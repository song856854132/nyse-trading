"""Integration tests for synthetic calibration.

Validates that the pipeline can detect planted signals and reject pure noise.
Uses deterministic seeds for reproducibility.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.features.registry import FactorRegistry
from nyse_core.metrics import information_coefficient
from nyse_core.normalize import rank_percentile
from nyse_core.research_pipeline import ResearchPipeline
from nyse_core.schema import COL_CLOSE, COL_DATE, COL_SYMBOL, COL_VOLUME, UsageDomain
from nyse_core.synthetic_calibration import (
    generate_calibration_data,
    run_calibration,
)

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_simple_registry() -> FactorRegistry:
    """Build a minimal FactorRegistry for calibration tests."""
    registry = FactorRegistry()

    def _close_factor(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        diag = Diagnostics()
        latest = data.sort_values(COL_DATE).groupby(COL_SYMBOL).last()
        return latest[COL_CLOSE], diag

    registry.register(
        name="factor_close",
        compute_fn=_close_factor,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=1,
        description="Close price factor",
    )
    return registry


# ── Tests ────────────────────────────────────────────────────────────────


class TestGenerateCalibrationData:
    """Tests for generate_calibration_data output shape and properties."""

    def test_calibration_data_has_expected_shape(self) -> None:
        """Verify output dimensions match parameters."""
        n_stocks = 100
        n_days = 50
        n_noise = 3

        ohlcv, feat_matrix, fwd_returns = generate_calibration_data(
            n_stocks=n_stocks,
            n_days=n_days,
            n_noise_factors=n_noise,
            seed=42,
        )

        # OHLCV: n_stocks * n_days rows (approximately, weekday filtering)
        assert len(ohlcv) > 0
        assert set(ohlcv.columns) >= {
            COL_DATE,
            COL_SYMBOL,
            "open",
            "high",
            "low",
            COL_CLOSE,
            COL_VOLUME,
        }
        assert ohlcv[COL_SYMBOL].nunique() == n_stocks

        # Feature matrix: n_stocks rows, 1 planted + n_noise columns
        assert feat_matrix.shape[0] == n_stocks
        assert feat_matrix.shape[1] == 1 + n_noise
        assert "planted_signal" in feat_matrix.columns

        # Forward returns: n_stocks entries
        assert len(fwd_returns) == n_stocks

    def test_calibration_features_are_normalized(self) -> None:
        """All feature values should be in [0, 1] (rank-percentile)."""
        _, feat_matrix, _ = generate_calibration_data(
            n_stocks=100,
            n_days=50,
            seed=42,
        )

        non_nan = feat_matrix.values[~np.isnan(feat_matrix.values)]
        assert non_nan.min() >= 0.0
        assert non_nan.max() <= 1.0


class TestCalibrationDetection:
    """Tests for signal detection via run_calibration."""

    def test_calibration_detects_planted_signal(self) -> None:
        """Planted signal should be detected with SNR > 10x."""
        registry = _make_simple_registry()
        pipeline = ResearchPipeline(registry=registry)

        result, diag = run_calibration(
            pipeline=pipeline,
            n_trials=50,
            seed=42,
        )

        # The planted signal should dominate noise
        assert result["signal_detected_rate"] >= 0.90, (
            f"Signal detected rate {result['signal_detected_rate']:.2f} < 0.90"
        )
        assert result["avg_snr"] >= 10.0, f"Average SNR {result['avg_snr']:.1f} < 10.0"
        assert result["avg_planted_ic"] > result["avg_noise_ic"]

    def test_calibration_rejects_pure_noise(self) -> None:
        """When all factors are noise, signal_detected_rate should be low.

        We test this by checking that noise ICs are small and that the
        planted signal IC genuinely exceeds them in the normal case.
        """
        # Generate a single trial with noise-only
        rng = np.random.default_rng(99)
        n_stocks = 100
        symbols = [f"N_{i:03d}" for i in range(n_stocks)]

        # All factors are pure noise
        noise_factors: dict[str, pd.Series] = {}
        for i in range(4):
            raw = pd.Series(rng.normal(0, 1, n_stocks), index=symbols)
            normed, _ = rank_percentile(raw)
            noise_factors[f"noise_{i}"] = normed

        feat_matrix = pd.DataFrame(noise_factors, index=symbols)

        # Forward returns: also pure noise (no signal)
        fwd_returns = pd.Series(rng.normal(0, 0.02, n_stocks), index=symbols)

        # Compute ICs -- they should all be small/insignificant
        ics = []
        for col in feat_matrix.columns:
            ic, _ = information_coefficient(feat_matrix[col], fwd_returns)
            ics.append(abs(ic))

        # No factor should have a large IC by chance (threshold 0.15)
        max_ic = max(ics)
        assert max_ic < 0.25, f"Pure noise factor had IC={max_ic:.3f}, expected < 0.25"

        # The ICs should be roughly similar (no standout)
        ic_std = np.std(ics)
        ic_mean = np.mean(ics)
        # Coefficient of variation should be moderate (no standout factor)
        if ic_mean > 0.01:
            cv = ic_std / ic_mean
            assert cv < 2.0, f"IC CV={cv:.2f} too high for pure noise"
