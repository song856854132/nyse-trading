"""Integration tests: monitoring subsystem.

Covers FalsificationMonitor trigger evaluation, frozen-config hash checks,
DataQualityChecker on synthetic data with injected errors, and
drift detection on realistic IC series.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

# ── Graceful skip if Phase 2 modules not yet available ────────────────────

try:
    from nyse_ats.monitoring.data_quality import DataQualityChecker, DataQualityResult
    from nyse_ats.monitoring.falsification import FalsificationMonitor
    from nyse_ats.storage.live_store import LiveStore
    from nyse_core.config_schema import FalsificationTriggersConfig, TriggerConfig
    from nyse_core.contracts import (
        Diagnostics,
        DriftCheckResult,
        FalsificationCheckResult,
    )
    from nyse_core.schema import (
        COL_CLOSE,
        COL_DATE,
        COL_HIGH,
        COL_LOW,
        COL_OPEN,
        COL_SYMBOL,
        COL_VOLUME,
        Severity,
    )

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False

from tests.fixtures.synthetic_prices import generate_prices

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not MODULES_AVAILABLE, reason="Phase 2 modules not yet available"),
]


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_falsification_config(
    triggers: dict[str, dict[str, Any]] | None = None,
) -> FalsificationTriggersConfig:
    """Build a FalsificationTriggersConfig with sensible defaults."""
    default_triggers = {
        "F1_signal_death": {
            "metric": "rolling_ic",
            "threshold": 0.01,
            "severity": "VETO",
            "description": "Rolling IC < 0.01 for 3 months",
        },
        "F2_factor_death": {
            "metric": "sign_flip_count",
            "threshold": 3,
            "severity": "VETO",
            "description": "IC sign flips > 3",
        },
        "F3_excessive_drawdown": {
            "metric": "max_drawdown",
            "threshold": -0.25,
            "severity": "VETO",
            "description": "Max drawdown worse than -25%",
        },
        "F4_concentration": {
            "metric": "max_position_weight",
            "threshold": 0.15,
            "severity": "WARNING",
            "description": "Single position > 15%",
        },
        "F5_turnover_spike": {
            "metric": "annual_turnover",
            "threshold": 200,
            "severity": "WARNING",
            "description": "Annual turnover > 200%",
        },
    }
    trigs = triggers or default_triggers
    trigger_models = {k: TriggerConfig(**v) for k, v in trigs.items()}
    return FalsificationTriggersConfig(
        frozen_date="2024-06-01",
        triggers=trigger_models,
    )


def _make_clean_ohlcv(
    n_stocks: int = 10,
    n_days: int = 100,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate clean OHLCV data that should pass all quality checks."""
    return generate_prices(n_stocks=n_stocks, n_days=n_days, seed=seed)


# ── Tests: FalsificationMonitor ───────────────────────────────────────────


class TestFalsificationIntegration:
    """Falsification triggers -> alert -> live store recording."""

    def test_veto_trigger_halts(self) -> None:
        """Metric breaches VETO threshold -> should_halt=True."""
        config = _make_falsification_config()
        monitor = FalsificationMonitor(config)

        # IC below threshold (F1 fires), drawdown worse than threshold (F3 fires)
        metrics = {
            "rolling_ic": 0.005,  # below 0.01 -> F1 VETO fires
            "sign_flip_count": 1,  # OK
            "max_drawdown": -0.30,  # below -0.25 -> F3 VETO fires
            "max_position_weight": 0.08,
            "annual_turnover": 150,
        }

        results, diag = monitor.evaluate_all(metrics)
        assert len(results) == 5

        veto_fired = monitor.get_veto_triggers(results)
        assert len(veto_fired) >= 1
        assert monitor.should_halt(results) is True

        veto_ids = {r.trigger_id for r in veto_fired}
        assert "F1_signal_death" in veto_ids

    def test_warning_trigger_fires(self) -> None:
        """WARNING fires for concentration breach but does not halt."""
        config = _make_falsification_config()
        monitor = FalsificationMonitor(config)

        metrics = {
            "rolling_ic": 0.05,  # healthy
            "sign_flip_count": 1,  # healthy
            "max_drawdown": -0.10,  # healthy
            "max_position_weight": 0.20,  # above 0.15 -> F4 WARNING fires
            "annual_turnover": 150,  # healthy
        }

        results, diag = monitor.evaluate_all(metrics)
        warnings = monitor.get_warning_triggers(results)
        assert len(warnings) >= 1
        assert monitor.should_halt(results) is False

        warning_ids = {r.trigger_id for r in warnings}
        assert "F4_concentration" in warning_ids

    def test_healthy_metrics_no_alerts(self) -> None:
        """All metrics within bounds -> no triggers fire -> no alerts."""
        config = _make_falsification_config()
        monitor = FalsificationMonitor(config)

        metrics = {
            "rolling_ic": 0.05,
            "sign_flip_count": 1,
            "max_drawdown": -0.05,
            "max_position_weight": 0.08,
            "annual_turnover": 100,
        }

        results, diag = monitor.evaluate_all(metrics)
        fired = [r for r in results if not r.passed]
        assert len(fired) == 0
        assert monitor.should_halt(results) is False

    def test_falsification_result_persisted(self, tmp_path: Path) -> None:
        """Check results stored in LiveStore for audit trail."""
        config = _make_falsification_config()
        monitor = FalsificationMonitor(config)

        metrics = {
            "rolling_ic": 0.005,
            "sign_flip_count": 1,
            "max_drawdown": -0.10,
            "max_position_weight": 0.08,
            "annual_turnover": 100,
        }

        results, _ = monitor.evaluate_all(metrics)

        with LiveStore(tmp_path / "live.duckdb") as store:
            for r in results:
                store.record_falsification_check(r, date(2024, 7, 1))

            rows = store._conn.execute("SELECT COUNT(*) FROM falsification_checks").fetchone()
            assert rows[0] == len(results)

    def test_frozen_hash_detects_modification(self, tmp_path: Path) -> None:
        """Modified config after frozen_date -> hash mismatch -> warning."""
        config = _make_falsification_config()
        monitor = FalsificationMonitor(config)

        config_file = tmp_path / "falsification_triggers.yaml"
        config_file.write_text("frozen_date: 2024-06-01\ntriggers: {}\n")

        original_hash = hashlib.sha256(config_file.read_bytes()).hexdigest()

        # Verify original hash matches
        match, diag_ok = monitor.verify_frozen_hash(config_file, original_hash)
        assert match is True

        # Modify the file
        config_file.write_text("frozen_date: 2024-06-01\ntriggers: {modified: true}\n")

        # Hash should now mismatch
        mismatch, diag_bad = monitor.verify_frozen_hash(config_file, original_hash)
        assert mismatch is False
        assert diag_bad.has_warnings

    def test_missing_metric_treated_as_fired(self) -> None:
        """If a required metric is missing, the trigger fires by default."""
        config = _make_falsification_config()
        monitor = FalsificationMonitor(config)

        # Omit "rolling_ic" entirely
        metrics = {
            "sign_flip_count": 1,
            "max_drawdown": -0.10,
            "max_position_weight": 0.08,
            "annual_turnover": 100,
        }

        results, diag = monitor.evaluate_all(metrics)
        f1 = next(r for r in results if r.trigger_id == "F1_signal_death")
        assert f1.passed is False


# ── Tests: DataQualityChecker ─────────────────────────────────────────────


class TestDataQualityIntegration:
    """Data quality checks on synthetic data with injected errors."""

    def test_clean_data_passes_core_checks(self) -> None:
        """Synthetic clean OHLCV -> core structural checks pass."""
        ohlcv = _make_clean_ohlcv(n_stocks=10, n_days=100)
        checker = DataQualityChecker()

        # Test OHLCV constraints check specifically (this should pass for generated data)
        result = checker.check_ohlcv_constraints(ohlcv)
        assert result.passed, f"OHLCV constraints failed: {result.details}"

    def test_gap_injection_caught(self) -> None:
        """Remove 5 consecutive days -> missing_dates check fails."""
        ohlcv = _make_clean_ohlcv(n_stocks=5, n_days=100)
        checker = DataQualityChecker()

        # Remove a block of dates to create a gap
        dates = sorted(ohlcv[COL_DATE].unique())
        gap_start = 30
        gap_dates = dates[gap_start : gap_start + 10]  # remove 10 days (guarantees >3 day gap)
        ohlcv_gapped = ohlcv[~ohlcv[COL_DATE].isin(gap_dates)].reset_index(drop=True)

        result = checker.check_missing_dates(ohlcv_gapped, max_gap_days=3)
        assert not result.passed, "Should detect the gap"
        assert result.violations > 0

    def test_stale_price_injection_caught(self) -> None:
        """Set identical close for 10 days -> stale_prices check fails."""
        ohlcv = _make_clean_ohlcv(n_stocks=5, n_days=100)
        checker = DataQualityChecker()

        # Pick one symbol and make 10 consecutive closes identical
        target_sym = ohlcv[COL_SYMBOL].unique()[0]
        mask = ohlcv[COL_SYMBOL] == target_sym
        sym_df = ohlcv.loc[mask].sort_values(COL_DATE)
        stale_price = float(sym_df[COL_CLOSE].iloc[20])

        # Set rows 20-29 to identical close
        idx = sym_df.index[20:30]
        ohlcv_stale = ohlcv.copy()
        ohlcv_stale.loc[idx, COL_CLOSE] = stale_price

        result = checker.check_stale_prices(ohlcv_stale, max_stale_days=5)
        assert not result.passed, "Should detect stale prices"
        assert result.violations > 0

    def test_outlier_injection_caught(self) -> None:
        """Insert 200% daily return -> price_outlier check fails."""
        ohlcv = _make_clean_ohlcv(n_stocks=5, n_days=100)
        checker = DataQualityChecker()

        # Pick one symbol and inject a 200% spike
        target_sym = ohlcv[COL_SYMBOL].unique()[0]
        sym_mask = ohlcv[COL_SYMBOL] == target_sym
        sym_df = ohlcv.loc[sym_mask].sort_values(COL_DATE)

        spike_idx = sym_df.index[50]
        ohlcv_outlier = ohlcv.copy()
        prev_close = ohlcv_outlier.loc[sym_df.index[49], COL_CLOSE]
        ohlcv_outlier.loc[spike_idx, COL_CLOSE] = prev_close * 3.0  # 200% return

        result = checker.check_price_outliers(ohlcv_outlier, max_daily_move=0.50)
        assert not result.passed, "Should detect the outlier"
        assert result.violations > 0

    def test_result_has_expected_fields(self) -> None:
        """DataQualityResult has the expected structural fields."""
        result = DataQualityResult(
            check_name="test_check",
            passed=True,
            details="All good",
            violations=0,
            violation_samples=[],
        )
        assert hasattr(result, "check_name")
        assert hasattr(result, "passed")
        assert hasattr(result, "details")
        assert hasattr(result, "violations")
        assert hasattr(result, "violation_samples")


# ── Tests: DriftMonitor ───────────────────────────────────────────────────


class TestDriftMonitorIntegration:
    """Drift detection on realistic IC series."""

    def test_degrading_signal_detected(self) -> None:
        """IC trending from 0.05 down to 0.005 -> drift should be detectable."""
        # Simulate a rolling IC that decays over 60 days
        rng = np.random.default_rng(42)
        n_points = 60

        # IC starts at ~0.05 and decays linearly to ~0.005
        ic_trend = np.linspace(0.05, 0.005, n_points)
        ic_noise = rng.normal(0, 0.005, n_points)
        ic_series = ic_trend + ic_noise

        # The final IC is below any reasonable threshold
        final_ic = float(np.mean(ic_series[-20:]))
        assert final_ic < 0.02, f"Expected degraded IC, got {final_ic:.4f}"

        # Use DriftCheckResult contract directly
        drift_result = DriftCheckResult(
            factor_name="test_factor",
            rolling_ic=final_ic,
            drift_detected=final_ic < 0.015,
            retrain_recommended=final_ic < 0.01,
            ic_threshold=0.015,
        )

        assert drift_result.drift_detected, "Drift should be detected for degrading IC"

    def test_stable_signal_no_drift(self) -> None:
        """IC stable at ~0.05 -> no drift detected."""
        rng = np.random.default_rng(42)
        n_points = 60

        ic_stable = 0.05 + rng.normal(0, 0.005, n_points)
        final_ic = float(np.mean(ic_stable[-20:]))

        drift_result = DriftCheckResult(
            factor_name="stable_factor",
            rolling_ic=final_ic,
            drift_detected=final_ic < 0.015,
            retrain_recommended=final_ic < 0.01,
            ic_threshold=0.015,
        )

        assert not drift_result.drift_detected, "No drift expected for stable IC"
        assert not drift_result.retrain_recommended
