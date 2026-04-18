"""Unit tests for DriftMonitor (rolling IC + retrain trigger)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_ats.monitoring.drift_monitor import DriftMonitor
from nyse_core.contracts import DriftCheckResult

# ── Helpers ─────────────────────────────────────────────────────────────────


def _healthy_ic(n: int = 60) -> pd.Series:
    """IC series comfortably above default threshold (0.015)."""
    rng = np.random.default_rng(42)
    return pd.Series(rng.normal(0.04, 0.005, n))


def _drifted_stable_ic(n: int = 60) -> pd.Series:
    """IC below threshold but with a slight upward trend (not declining)."""
    # Mean well below 0.015, but slope is positive → retrain not recommended
    return pd.Series(np.linspace(0.003, 0.008, n))


def _drifted_declining_ic(n: int = 60) -> pd.Series:
    """IC below threshold AND declining (negative slope)."""
    # Start at 0.012, end near 0.002 — mean < 0.015, slope < 0
    return pd.Series(np.linspace(0.012, 0.002, n))


# ── Tests ───────────────────────────────────────────────────────────────────


class TestDriftMonitor:
    def setup_method(self) -> None:
        self.monitor = DriftMonitor(ic_threshold=0.015, window_days=60)

    # -- Drift detected when IC below threshold --------------------------------

    def test_drift_detected_low_ic(self) -> None:
        result, diag = self.monitor.check_factor_drift("momentum", _drifted_stable_ic())
        assert result.drift_detected is True
        assert result.rolling_ic < 0.015

    # -- No drift when IC above threshold --------------------------------------

    def test_no_drift_healthy_ic(self) -> None:
        result, diag = self.monitor.check_factor_drift("value", _healthy_ic())
        assert result.drift_detected is False
        assert result.retrain_recommended is False
        assert not diag.has_errors

    # -- Retrain recommended: drift + downward trend ---------------------------

    def test_retrain_when_drift_and_declining(self) -> None:
        result, _ = self.monitor.check_factor_drift("quality", _drifted_declining_ic())
        assert result.drift_detected is True
        assert result.retrain_recommended is True

    # -- No retrain when drift but stable IC -----------------------------------

    def test_no_retrain_drift_but_stable(self) -> None:
        result, _ = self.monitor.check_factor_drift("size", _drifted_stable_ic())
        assert result.drift_detected is True
        # Stable noise around a low mean — slope should be ~0; retrain not recommended
        # (random seed 42 produces a near-zero slope for normal noise)
        assert result.retrain_recommended is False

    # -- check_all_factors with mixed results ----------------------------------

    def test_check_all_factors_mixed(self) -> None:
        ic_history = {
            "momentum": _healthy_ic(),
            "value": _drifted_declining_ic(),
        }
        results, diag = self.monitor.check_all_factors(ic_history)
        assert len(results) == 2
        by_name = {r.factor_name: r for r in results}
        assert by_name["momentum"].drift_detected is False
        assert by_name["value"].drift_detected is True

    # -- should_retrain aggregation --------------------------------------------

    def test_should_retrain_true_when_any_retrain(self) -> None:
        ic_history = {
            "momentum": _healthy_ic(),
            "value": _drifted_declining_ic(),
        }
        results, _ = self.monitor.check_all_factors(ic_history)
        assert self.monitor.should_retrain(results) is True

    def test_should_retrain_false_all_healthy(self) -> None:
        ic_history = {
            "momentum": _healthy_ic(),
            "value": _healthy_ic(),
        }
        results, _ = self.monitor.check_all_factors(ic_history)
        assert self.monitor.should_retrain(results) is False

    # -- Edge cases ------------------------------------------------------------

    def test_empty_ic_series(self) -> None:
        result, diag = self.monitor.check_factor_drift("empty", pd.Series(dtype=float))
        assert result.drift_detected is True
        assert result.retrain_recommended is True
        assert diag.has_warnings

    def test_result_type(self) -> None:
        result, _ = self.monitor.check_factor_drift("test", _healthy_ic())
        assert isinstance(result, DriftCheckResult)
        assert result.ic_threshold == 0.015
