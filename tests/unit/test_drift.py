"""Unit tests for pure drift detection logic."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from nyse_core.drift import (
    DriftReport,
    assess_drift,
    detect_ic_drift,
    detect_model_decay,
    detect_sign_flips,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_ic_series(values: list[float], start: str = "2023-01-01") -> pd.Series:
    """Create an IC time-series from a list of values."""
    idx = pd.bdate_range(start, periods=len(values))
    return pd.Series(values, index=idx)


def _make_healthy_ic(n_days: int = 80, mean: float = 0.04, seed: int = 42) -> pd.Series:
    """IC series well above default threshold of 0.015."""
    rng = np.random.default_rng(seed)
    values = mean + rng.normal(0, 0.005, size=n_days)
    return _make_ic_series(values.tolist())


def _make_drifting_ic(n_days: int = 80, seed: int = 42) -> pd.Series:
    """IC series that trends downward below threshold."""
    rng = np.random.default_rng(seed)
    values = np.linspace(0.03, -0.01, n_days) + rng.normal(0, 0.002, size=n_days)
    return _make_ic_series(values.tolist())


# ── IC Drift Tests ───────────────────────────────────────────────────────────


class TestDetectICDriftHealthy:
    """All ICs above threshold -> no drift detected."""

    def test_detect_ic_drift_healthy(self):
        ic_history = {
            "momentum": _make_healthy_ic(seed=1),
            "value": _make_healthy_ic(seed=2),
            "quality": _make_healthy_ic(seed=3),
        }
        results, diag = detect_ic_drift(ic_history, threshold=0.015)

        assert len(results) == 3
        for r in results:
            assert not r.drift_detected, f"{r.factor_name} should not be drifting"
        assert not diag.has_errors


class TestDetectICDriftSingleFactorDrifting:
    """One factor below threshold, others healthy."""

    def test_detect_ic_drift_single_factor_drifting(self):
        ic_history = {
            "momentum": _make_healthy_ic(seed=1),
            "bad_factor": _make_drifting_ic(seed=2),
            "quality": _make_healthy_ic(seed=3),
        }
        results, diag = detect_ic_drift(ic_history, threshold=0.015)

        drifting = [r for r in results if r.drift_detected]
        assert len(drifting) == 1
        assert drifting[0].factor_name == "bad_factor"


class TestDetectICDriftAllFactorsDrifting:
    """All factors below threshold."""

    def test_detect_ic_drift_all_factors_drifting(self):
        ic_history = {
            "f1": _make_drifting_ic(seed=1),
            "f2": _make_drifting_ic(seed=2),
            "f3": _make_drifting_ic(seed=3),
        }
        results, diag = detect_ic_drift(ic_history, threshold=0.015)

        for r in results:
            assert r.drift_detected, f"{r.factor_name} should be drifting"


# ── Sign Flip Tests ──────────────────────────────────────────────────────────


class TestDetectSignFlipsNone:
    """Stable positive IC -> no sign flips."""

    def test_detect_sign_flips_none(self):
        ic_history = {
            "stable": _make_ic_series([0.03] * 42),
        }
        flips, diag = detect_sign_flips(ic_history, window_months=2)

        assert flips["stable"] == 0
        assert not diag.has_errors


class TestDetectSignFlipsMultiple:
    """Alternating positive/negative IC -> many sign flips."""

    def test_detect_sign_flips_multiple(self):
        # Alternate sign every day for 42 days
        values = [0.02 * ((-1) ** i) for i in range(42)]
        ic_history = {
            "volatile": _make_ic_series(values),
        }
        flips, diag = detect_sign_flips(ic_history, window_months=2)

        assert flips["volatile"] > 3, "Expected many sign flips for alternating IC"
        # Should trigger a warning (F2 VETO risk)
        assert diag.has_warnings


# ── Model Decay Tests ────────────────────────────────────────────────────────


class TestDetectModelDecayHealthy:
    """Good predictions -> positive R-squared."""

    def test_detect_model_decay_healthy(self):
        idx = pd.bdate_range("2023-01-01", periods=80)
        rng = np.random.default_rng(42)
        actual = pd.Series(rng.normal(0.001, 0.01, size=80), index=idx)
        # Predictions closely track actual
        predicted = actual + rng.normal(0, 0.002, size=80)

        r2, diag = detect_model_decay(predicted, actual, window_days=60)

        assert r2 > 0.0, f"Expected positive R2 for good predictions, got {r2}"
        assert not diag.has_errors


class TestDetectModelDecayPoor:
    """Random predictions -> near-zero or negative R-squared."""

    def test_detect_model_decay_poor(self):
        idx = pd.bdate_range("2023-01-01", periods=80)
        rng = np.random.default_rng(42)
        actual = pd.Series(rng.normal(0.001, 0.01, size=80), index=idx)
        # Predictions are unrelated noise
        predicted = pd.Series(rng.normal(0.001, 0.01, size=80), index=idx)

        r2, diag = detect_model_decay(predicted, actual, window_days=60)

        assert r2 < 0.5, f"Expected low R2 for random predictions, got {r2}"


# ── Full Assessment Tests ────────────────────────────────────────────────────


class TestAssessDriftComprehensive:
    """Full drift assessment with mixed factor health."""

    def test_assess_drift_comprehensive(self):
        ic_history = {
            "good_1": _make_healthy_ic(seed=1),
            "good_2": _make_healthy_ic(seed=2),
            "bad_1": _make_drifting_ic(seed=3),
        }
        idx = pd.bdate_range("2023-01-01", periods=80)
        rng = np.random.default_rng(42)
        actual = pd.Series(rng.normal(0.001, 0.01, 80), index=idx)
        predicted = actual + rng.normal(0, 0.002, 80)

        report, diag = assess_drift(
            ic_history,
            predicted_returns=predicted,
            actual_returns=actual,
        )

        assert isinstance(report, DriftReport)
        assert report.overall_drift_detected  # bad_1 is drifting
        assert len(report.factor_drifts) == 3
        assert report.retrain_urgency in ("low", "medium", "high")
        assert not math.isnan(report.model_r2_rolling)


class TestRetrainUrgencyLevels:
    """Verify urgency levels match fraction of drifting factors."""

    def test_retrain_urgency_none(self):
        """No drifting factors -> urgency 'none'."""
        ic_history = {f"f{i}": _make_healthy_ic(seed=i) for i in range(4)}
        report, _ = assess_drift(ic_history)
        assert report.retrain_urgency == "none"

    def test_retrain_urgency_low(self):
        """1 of 8 factors drifting -> urgency 'low' (12.5%)."""
        ic_history = {f"f{i}": _make_healthy_ic(seed=i) for i in range(7)}
        ic_history["bad"] = _make_drifting_ic(seed=99)
        report, _ = assess_drift(ic_history)
        assert report.retrain_urgency == "low"

    def test_retrain_urgency_medium(self):
        """2 of 6 factors drifting -> urgency 'medium' (33%)."""
        ic_history = {
            "g1": _make_healthy_ic(seed=1),
            "g2": _make_healthy_ic(seed=2),
            "g3": _make_healthy_ic(seed=5),
            "g4": _make_healthy_ic(seed=6),
            "b1": _make_drifting_ic(seed=3),
            "b2": _make_drifting_ic(seed=4),
        }
        report, _ = assess_drift(ic_history)
        # 33% drifting (>25%, <=50%) -> "medium"
        assert report.retrain_urgency == "medium"

    def test_retrain_urgency_high(self):
        """All factors drifting -> urgency 'high'."""
        ic_history = {f"f{i}": _make_drifting_ic(seed=i) for i in range(4)}
        report, _ = assess_drift(ic_history)
        assert report.retrain_urgency == "high"


# ── Edge Cases ───────────────────────────────────────────────────────────────


class TestEmptyICHistory:
    """Empty IC history should not crash and return empty results."""

    def test_empty_ic_history(self):
        results, diag = detect_ic_drift({})
        assert results == []
        assert diag.has_warnings

    def test_empty_sign_flips(self):
        flips, diag = detect_sign_flips({})
        assert flips == {}
        assert diag.has_warnings

    def test_assess_drift_empty(self):
        report, diag = assess_drift({})
        assert len(report.factor_drifts) == 0
        assert report.retrain_urgency == "none"
        assert not report.overall_drift_detected
