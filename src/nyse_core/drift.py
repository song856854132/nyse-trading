"""Pure drift detection logic for factor models.

Detects three types of drift:
  1. IC drift: rolling IC falls below threshold
  2. Factor sign flip: factor's directional bet reverses
  3. Model decay: out-of-sample R-squared drops below threshold

All functions are pure -- no I/O, no logging.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from nyse_core.contracts import Diagnostics, DriftCheckResult

if TYPE_CHECKING:
    import pandas as pd

_MOD = "drift"


@dataclass(frozen=True)
class DriftReport:
    """Comprehensive drift assessment for a model."""

    factor_drifts: list[DriftCheckResult]
    sign_flips: dict[str, int]
    model_r2_rolling: float
    overall_drift_detected: bool
    retrain_recommended: bool
    retrain_urgency: str  # "none", "low", "medium", "high"


# ── IC Drift Detection ──────────────────────────────────────────────────────


def detect_ic_drift(
    ic_history: dict[str, pd.Series],
    threshold: float = 0.015,
    window_days: int = 60,
) -> tuple[list[DriftCheckResult], Diagnostics]:
    """Check each factor's rolling IC against threshold.

    Parameters
    ----------
    ic_history : dict[str, pd.Series]
        Mapping factor_name -> time-series of IC values.
    threshold : float
        Minimum acceptable mean IC over the rolling window.
    window_days : int
        Number of trailing days for the rolling window.

    Returns
    -------
    tuple[list[DriftCheckResult], Diagnostics]
    """
    diag = Diagnostics()
    src = f"{_MOD}.detect_ic_drift"
    results: list[DriftCheckResult] = []

    if not ic_history:
        diag.warning(src, "Empty IC history provided.")
        return results, diag

    for factor_name, ic_series in ic_history.items():
        if ic_series is None or len(ic_series) == 0:
            results.append(
                DriftCheckResult(
                    factor_name=factor_name,
                    rolling_ic=float("nan"),
                    drift_detected=True,
                    retrain_recommended=True,
                    ic_threshold=threshold,
                )
            )
            diag.warning(src, f"No IC data for factor '{factor_name}'.")
            continue

        window = ic_series.tail(window_days).dropna()
        if len(window) == 0:
            results.append(
                DriftCheckResult(
                    factor_name=factor_name,
                    rolling_ic=float("nan"),
                    drift_detected=True,
                    retrain_recommended=True,
                    ic_threshold=threshold,
                )
            )
            diag.warning(src, f"All IC values NaN for factor '{factor_name}'.")
            continue

        mean_ic = float(window.mean())
        drift_detected = mean_ic < threshold

        # Retrain if drifting AND slope is negative
        retrain_recommended = False
        if drift_detected and len(window) >= 2:
            x = np.arange(len(window), dtype=float)
            y = window.values.astype(float)
            slope = float(np.polyfit(x, y, 1)[0])
            retrain_recommended = slope < 0.0

        results.append(
            DriftCheckResult(
                factor_name=factor_name,
                rolling_ic=mean_ic,
                drift_detected=drift_detected,
                retrain_recommended=retrain_recommended,
                ic_threshold=threshold,
            )
        )
        level = "info" if not drift_detected else "warning"
        getattr(diag, level)(
            src,
            f"Factor '{factor_name}': mean_ic={mean_ic:.4f}, threshold={threshold}, drift={drift_detected}.",
        )

    return results, diag


# ── Sign Flip Detection ─────────────────────────────────────────────────────


def detect_sign_flips(
    ic_history: dict[str, pd.Series],
    window_months: int = 2,
) -> tuple[dict[str, int], Diagnostics]:
    """Count sign flips (IC changes sign) per factor over window.

    A sign flip occurs when the IC value changes from positive to negative
    or vice versa between consecutive observations.

    F2 trigger: >3 sign flips in 2 months = VETO.

    Parameters
    ----------
    ic_history : dict[str, pd.Series]
        Mapping factor_name -> time-series of IC values.
    window_months : int
        Number of trailing months (~21 trading days each) to consider.

    Returns
    -------
    tuple[dict[str, int], Diagnostics]
        (factor_name -> flip count, diagnostics)
    """
    diag = Diagnostics()
    src = f"{_MOD}.detect_sign_flips"
    flip_counts: dict[str, int] = {}

    if not ic_history:
        diag.warning(src, "Empty IC history provided.")
        return flip_counts, diag

    window_days = window_months * 21  # approximate trading days per month

    for factor_name, ic_series in ic_history.items():
        if ic_series is None or len(ic_series) == 0:
            flip_counts[factor_name] = 0
            continue

        window = ic_series.tail(window_days).dropna()
        if len(window) < 2:
            flip_counts[factor_name] = 0
            continue

        values = window.values.astype(float)
        signs = np.sign(values)
        # Count transitions where sign changes (ignoring zeros)
        nonzero_mask = signs != 0
        nonzero_signs = signs[nonzero_mask]

        if len(nonzero_signs) < 2:
            flip_counts[factor_name] = 0
            continue

        flips = int(np.sum(nonzero_signs[1:] != nonzero_signs[:-1]))
        flip_counts[factor_name] = flips

        if flips > 3:
            diag.warning(
                src,
                f"Factor '{factor_name}': {flips} sign flips in {window_months} months (F2 VETO risk).",
            )

    return flip_counts, diag


# ── Model Decay Detection ───────────────────────────────────────────────────


def detect_model_decay(
    predicted_returns: pd.Series,
    actual_returns: pd.Series,
    window_days: int = 60,
) -> tuple[float, Diagnostics]:
    """Rolling R-squared between predicted and actual portfolio returns.

    Parameters
    ----------
    predicted_returns : pd.Series
        Predicted return series.
    actual_returns : pd.Series
        Actual return series (same index as predicted).
    window_days : int
        Rolling window length.

    Returns
    -------
    tuple[float, Diagnostics]
        (rolling R-squared, diagnostics)
    """
    diag = Diagnostics()
    src = f"{_MOD}.detect_model_decay"

    if predicted_returns is None or actual_returns is None:
        diag.warning(src, "Missing predicted or actual returns.")
        return float("nan"), diag

    if len(predicted_returns) == 0 or len(actual_returns) == 0:
        diag.warning(src, "Empty predicted or actual returns.")
        return float("nan"), diag

    # Align on common index
    common_idx = predicted_returns.index.intersection(actual_returns.index)
    if len(common_idx) == 0:
        diag.warning(src, "No overlapping dates between predicted and actual.")
        return float("nan"), diag

    pred = predicted_returns.loc[common_idx].tail(window_days).dropna()
    actual = actual_returns.loc[common_idx].tail(window_days).dropna()

    # Re-align after dropna
    shared = pred.index.intersection(actual.index)
    if len(shared) < 2:
        diag.warning(src, "Insufficient data points for R-squared calculation.")
        return float("nan"), diag

    pred = pred.loc[shared]
    actual = actual.loc[shared]

    # Compute R-squared: 1 - SS_res / SS_tot
    ss_res = float(np.sum((actual.values - pred.values) ** 2))
    ss_tot = float(np.sum((actual.values - actual.values.mean()) ** 2))

    if ss_tot == 0.0:
        diag.warning(src, "Zero variance in actual returns.")
        return float("nan"), diag

    r2 = 1.0 - ss_res / ss_tot
    diag.info(src, f"Rolling R2={r2:.4f} over {len(shared)} days.")
    return r2, diag


# ── Full Drift Assessment ───────────────────────────────────────────────────


def assess_drift(
    ic_history: dict[str, pd.Series],
    predicted_returns: pd.Series | None = None,
    actual_returns: pd.Series | None = None,
    ic_threshold: float = 0.015,
    sign_flip_threshold: int = 3,
    r2_threshold: float = 0.0,
) -> tuple[DriftReport, Diagnostics]:
    """Full drift assessment combining all three detection methods.

    retrain_urgency:
      - "high" if >50% factors drifting
      - "medium" if >25% factors drifting
      - "low" if any factor drifting
      - "none" otherwise

    Parameters
    ----------
    ic_history : dict[str, pd.Series]
        Per-factor IC time series.
    predicted_returns : pd.Series | None
        Predicted portfolio returns (optional).
    actual_returns : pd.Series | None
        Actual portfolio returns (optional).
    ic_threshold : float
        IC drift threshold.
    sign_flip_threshold : int
        Max allowed sign flips before flagging.
    r2_threshold : float
        Minimum acceptable R-squared.

    Returns
    -------
    tuple[DriftReport, Diagnostics]
    """
    diag = Diagnostics()
    src = f"{_MOD}.assess_drift"

    # 1. IC drift
    factor_drifts, ic_diag = detect_ic_drift(ic_history, threshold=ic_threshold)
    diag.merge(ic_diag)

    # 2. Sign flips
    sign_flips, sf_diag = detect_sign_flips(ic_history)
    diag.merge(sf_diag)

    # 3. Model decay
    r2 = float("nan")
    if predicted_returns is not None and actual_returns is not None:
        r2, decay_diag = detect_model_decay(predicted_returns, actual_returns)
        diag.merge(decay_diag)

    # Determine overall drift status
    n_factors = len(factor_drifts)
    n_drifting = sum(1 for d in factor_drifts if d.drift_detected)
    any_sign_flip_veto = any(v > sign_flip_threshold for v in sign_flips.values())
    model_decayed = (not np.isnan(r2)) and r2 < r2_threshold

    overall_drift = n_drifting > 0 or any_sign_flip_veto or model_decayed

    # Retrain urgency based on fraction of drifting factors
    if n_factors == 0:
        urgency = "none"
    elif n_drifting / n_factors > 0.50:
        urgency = "high"
    elif n_drifting / n_factors > 0.25:
        urgency = "medium"
    elif n_drifting > 0:
        urgency = "low"
    else:
        urgency = "none"

    # Elevate urgency if sign flip veto or model decay
    if (any_sign_flip_veto or model_decayed) and urgency in ("none", "low"):
        urgency = "medium"

    retrain_recommended = overall_drift

    diag.info(
        src,
        f"Drift assessment: {n_drifting}/{n_factors} factors drifting, urgency={urgency}, r2={r2:.4f}.",
    )

    report = DriftReport(
        factor_drifts=factor_drifts,
        sign_flips=sign_flips,
        model_r2_rolling=r2,
        overall_drift_detected=overall_drift,
        retrain_recommended=retrain_recommended,
        retrain_urgency=urgency,
    )

    return report, diag
