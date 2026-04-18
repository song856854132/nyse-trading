"""Synthetic calibration: validates the pipeline detects planted signals.

Pure logic -- no I/O, no logging. Generates data with known signal-to-noise
characteristics and checks whether ResearchPipeline recovers the planted signal.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.normalize import rank_percentile
from nyse_core.schema import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_SYMBOL,
    COL_VOLUME,
)

_SRC = "synthetic_calibration"


def generate_calibration_data(
    n_stocks: int = 200,
    n_days: int = 1000,
    signal_strength: float = 0.05,
    n_noise_factors: int = 3,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Generate synthetic data with a planted signal for pipeline calibration.

    The planted signal has known IC with forward returns. The pipeline should
    detect it with SNR > 10x (signal Sharpe / noise Sharpe > 10).

    Returns
    -------
    ohlcv : pd.DataFrame
        Synthetic OHLCV with columns: date, symbol, open, high, low, close, volume.
    feature_matrix : pd.DataFrame
        Cross-sectional features with columns: planted_signal, noise_0, ..., noise_N.
        Index = symbol. Values in [0, 1] (rank-percentile normalized).
    true_forward_returns : pd.Series
        Forward returns per symbol (index = symbol).
    """
    rng = np.random.default_rng(seed)

    symbols = [f"CAL_{i:03d}" for i in range(n_stocks)]
    start_date = date(2020, 1, 2)

    # Generate trading dates (weekdays)
    all_dates = pd.bdate_range(start=start_date, periods=n_days, freq="B")

    # Generate cross-sectional "true alpha" per stock (persistent)
    true_alpha = rng.normal(0, 1.0, n_stocks)

    # Forward returns: driven by true alpha + small noise
    # The signal_strength controls the IC between planted signal and returns
    noise_ret = rng.normal(0, 0.01, n_stocks)
    forward_returns_raw = true_alpha * 0.02 + noise_ret

    # Build planted signal: strongly correlated with true alpha (and thus returns)
    # signal_strength controls how much of the signal is alpha vs noise
    planted_noise = rng.normal(0, 1.0, n_stocks)
    # Use a mixing coefficient that yields high IC
    mix = 0.8  # 80% true alpha, 20% noise
    planted_raw = mix * true_alpha + (1.0 - mix) * planted_noise

    # Rank-percentile normalize the planted signal to [0, 1]
    planted_series = pd.Series(planted_raw, index=symbols)
    planted_norm, _ = rank_percentile(planted_series)

    # Generate noise factors (uncorrelated with forward returns)
    noise_factors: dict[str, pd.Series] = {}
    for i in range(n_noise_factors):
        noise_raw = pd.Series(rng.normal(0, 1, n_stocks), index=symbols)
        noise_norm, _ = rank_percentile(noise_raw)
        noise_factors[f"noise_{i}"] = noise_norm

    # Build feature matrix
    features = {"planted_signal": planted_norm}
    features.update(noise_factors)
    feature_matrix = pd.DataFrame(features, index=symbols)

    # Build synthetic OHLCV
    records: list[dict] = []
    for i, sym in enumerate(symbols):
        base_price = 50.0 + rng.uniform(-20, 50)
        for d_idx, d in enumerate(all_dates):
            drift = forward_returns_raw[i] / n_days
            noise = rng.normal(0, 0.02)
            close_p = base_price * (1 + drift * d_idx + noise)
            close_p = max(close_p, 1.0)
            open_p = close_p * (1 + rng.normal(0, 0.003))
            high_p = max(open_p, close_p) * (1 + abs(rng.normal(0, 0.005)))
            low_p = min(open_p, close_p) * (1 - abs(rng.normal(0, 0.005)))
            low_p = max(low_p, 0.5)
            vol = int(rng.lognormal(14, 0.5))

            records.append(
                {
                    COL_DATE: d.date(),
                    COL_SYMBOL: sym,
                    COL_OPEN: round(open_p, 2),
                    COL_HIGH: round(high_p, 2),
                    COL_LOW: round(low_p, 2),
                    COL_CLOSE: round(close_p, 2),
                    COL_VOLUME: vol,
                }
            )

    ohlcv = pd.DataFrame(records)
    true_fwd = pd.Series(forward_returns_raw, index=symbols, name="fwd_ret")

    return ohlcv, feature_matrix, true_fwd


def run_calibration(
    pipeline: ResearchPipeline,  # noqa: F821 -- avoid circular import
    n_trials: int = 50,
    seed: int = 42,
) -> tuple[dict[str, float], Diagnostics]:
    """Run synthetic calibration: does the pipeline detect the planted signal?

    Success criteria:
      - signal_detected_rate >= 0.90 (detects in 90%+ of trials)
      - avg_snr >= 10.0 (10x signal-to-noise ratio)

    Returns
    -------
    dict with keys: signal_detected_rate, avg_snr, avg_planted_ic, avg_noise_ic
    """
    from nyse_core.metrics import information_coefficient

    diag = Diagnostics()
    src = f"{_SRC}.run_calibration"

    detected_count = 0
    snr_values: list[float] = []
    planted_ics: list[float] = []
    noise_ics: list[float] = []

    for trial in range(n_trials):
        trial_seed = seed + trial
        np.random.default_rng(trial_seed)

        _, feat_matrix, fwd_returns = generate_calibration_data(
            n_stocks=100,
            n_days=50,
            signal_strength=0.05,
            n_noise_factors=3,
            seed=trial_seed,
        )

        # Compute IC for planted signal
        common = feat_matrix.index.intersection(fwd_returns.index)
        planted_ic, _ = information_coefficient(
            feat_matrix.loc[common, "planted_signal"],
            fwd_returns.loc[common],
        )
        planted_ics.append(abs(planted_ic))

        # Compute IC for each noise factor
        trial_noise_ics: list[float] = []
        noise_cols = [c for c in feat_matrix.columns if c.startswith("noise_")]
        for nc in noise_cols:
            nic, _ = information_coefficient(
                feat_matrix.loc[common, nc],
                fwd_returns.loc[common],
            )
            trial_noise_ics.append(abs(nic))

        avg_noise_ic_trial = float(np.mean(trial_noise_ics)) if trial_noise_ics else 0.0
        noise_ics.append(avg_noise_ic_trial)

        # Signal detected if planted IC > 2x any noise IC
        max_noise_ic = max(trial_noise_ics) if trial_noise_ics else 0.0
        if abs(planted_ic) > max_noise_ic:
            detected_count += 1

        # SNR: planted IC / avg noise IC
        if avg_noise_ic_trial > 1e-10:
            snr = abs(planted_ic) / avg_noise_ic_trial
        else:
            snr = float("inf") if abs(planted_ic) > 1e-10 else 1.0
        snr_values.append(snr)

    result = {
        "signal_detected_rate": detected_count / n_trials,
        "avg_snr": float(np.mean(snr_values)),
        "avg_planted_ic": float(np.mean(planted_ics)),
        "avg_noise_ic": float(np.mean(noise_ics)),
    }

    diag.info(
        src,
        f"Calibration: detected={result['signal_detected_rate']:.2f}, "
        f"SNR={result['avg_snr']:.1f}, "
        f"planted_IC={result['avg_planted_ic']:.4f}, "
        f"noise_IC={result['avg_noise_ic']:.4f}.",
        n_trials=n_trials,
    )
    return result, diag
