"""Enhanced unit tests for FalsificationMonitor (F1-F8 triggers).

Thorough coverage of evaluate_all, veto/warning separation,
frozen hash verification, and boolean trigger edge cases.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from nyse_ats.monitoring.falsification import FalsificationMonitor
from nyse_core.config_schema import FalsificationTriggersConfig, TriggerConfig
from nyse_core.schema import Severity

# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_config(
    triggers: dict[str, dict] | None = None,
) -> FalsificationTriggersConfig:
    """Build a FalsificationTriggersConfig for testing."""
    default_triggers = {
        "F1_signal_death": {
            "metric": "rolling_ic_60d",
            "threshold": 0.01,
            "months": 2,
            "severity": "VETO",
            "description": "Rolling IC below 0.01 for 2+ months",
        },
        "F2_factor_death": {
            "metric": "core_factor_sign_flips",
            "threshold": 3,
            "months": 2,
            "severity": "VETO",
            "description": "3+ core factors flip sign",
        },
        "F3_excessive_drawdown": {
            "metric": "max_drawdown",
            "threshold": -0.25,
            "severity": "VETO",
            "description": "Max drawdown exceeds -25%",
        },
        "F4_concentration": {
            "metric": "max_single_stock_weight",
            "threshold": 0.15,
            "severity": "WARNING",
            "description": "Single stock weight exceeds 15%",
        },
        "F5_turnover_spike": {
            "metric": "monthly_turnover_pct",
            "threshold": 200,
            "severity": "WARNING",
            "description": "Monthly turnover exceeds 200%",
        },
        "F6_cost_drag": {
            "metric": "annual_cost_drag_pct",
            "threshold": 5.0,
            "severity": "WARNING",
            "description": "Annual cost drag exceeds 5%",
        },
        "F7_regime_anomaly": {
            "metric": "benchmark_split_adjusted",
            "threshold": False,
            "severity": "WARNING",
            "description": "Benchmark may not be split-adjusted",
        },
        "F8_data_staleness": {
            "metric": "max_feature_staleness_days",
            "threshold": 10,
            "severity": "WARNING",
            "description": "Most stale feature exceeds 10 days",
        },
    }
    raw = triggers or default_triggers
    return FalsificationTriggersConfig(
        frozen_date="2026-04-15",
        triggers={k: TriggerConfig(**v) for k, v in raw.items()},
    )


def _healthy_metrics() -> dict[str, float]:
    """Metric values where all triggers pass (healthy state)."""
    return {
        "rolling_ic_60d": 0.05,
        "core_factor_sign_flips": 1,
        "max_drawdown": -0.10,
        "max_single_stock_weight": 0.08,
        "monthly_turnover_pct": 100,
        "annual_cost_drag_pct": 2.0,
        "benchmark_split_adjusted": 0.0,
        "max_feature_staleness_days": 3,
    }


# ── Tests ───────────────────────────────────────────────────────────────────


class TestEvaluateAllHealthyMetrics:
    """All triggers pass with healthy metrics."""

    def setup_method(self) -> None:
        self.config = _make_config()
        self.monitor = FalsificationMonitor(self.config)

    def test_all_pass(self) -> None:
        results, diag = self.monitor.evaluate_all(_healthy_metrics())
        assert all(r.passed for r in results)
        assert len(results) == 8

    def test_no_errors_in_diagnostics(self) -> None:
        _, diag = self.monitor.evaluate_all(_healthy_metrics())
        assert not diag.has_errors

    def test_no_warnings_in_diagnostics(self) -> None:
        """Healthy metrics should not produce warnings about missing data."""
        _, diag = self.monitor.evaluate_all(_healthy_metrics())
        # There may be info-level messages but no warnings about missing metrics
        warning_msgs = [
            m for m in diag.messages if m.level.value == "WARNING" and "missing" in m.message.lower()
        ]
        assert len(warning_msgs) == 0


class TestEvaluateAllWithVetoTrigger:
    """VETO trigger fires correctly."""

    def setup_method(self) -> None:
        self.monitor = FalsificationMonitor(_make_config())

    def test_f1_veto_fires(self) -> None:
        metrics = _healthy_metrics()
        metrics["rolling_ic_60d"] = 0.005
        results, _ = self.monitor.evaluate_all(metrics)
        f1 = next(r for r in results if r.trigger_id == "F1_signal_death")
        assert f1.passed is False
        assert f1.severity == Severity.VETO

    def test_f2_veto_fires(self) -> None:
        metrics = _healthy_metrics()
        metrics["core_factor_sign_flips"] = 5
        results, _ = self.monitor.evaluate_all(metrics)
        f2 = next(r for r in results if r.trigger_id == "F2_factor_death")
        assert f2.passed is False
        assert f2.severity == Severity.VETO

    def test_f3_veto_fires(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = -0.30
        results, _ = self.monitor.evaluate_all(metrics)
        f3 = next(r for r in results if r.trigger_id == "F3_excessive_drawdown")
        assert f3.passed is False
        assert f3.severity == Severity.VETO


class TestEvaluateAllWithWarningTrigger:
    """WARNING trigger fires correctly."""

    def setup_method(self) -> None:
        self.monitor = FalsificationMonitor(_make_config())

    def test_f4_warning_fires(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_single_stock_weight"] = 0.20
        results, _ = self.monitor.evaluate_all(metrics)
        f4 = next(r for r in results if r.trigger_id == "F4_concentration")
        assert f4.passed is False
        assert f4.severity == Severity.WARNING

    def test_f5_warning_fires(self) -> None:
        metrics = _healthy_metrics()
        metrics["monthly_turnover_pct"] = 300
        results, _ = self.monitor.evaluate_all(metrics)
        f5 = next(r for r in results if r.trigger_id == "F5_turnover_spike")
        assert f5.passed is False
        assert f5.severity == Severity.WARNING

    def test_f6_warning_fires(self) -> None:
        metrics = _healthy_metrics()
        metrics["annual_cost_drag_pct"] = 6.0
        results, _ = self.monitor.evaluate_all(metrics)
        f6 = next(r for r in results if r.trigger_id == "F6_cost_drag")
        assert f6.passed is False
        assert f6.severity == Severity.WARNING

    def test_f8_warning_fires(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_feature_staleness_days"] = 15
        results, _ = self.monitor.evaluate_all(metrics)
        f8 = next(r for r in results if r.trigger_id == "F8_data_staleness")
        assert f8.passed is False
        assert f8.severity == Severity.WARNING


class TestMissingMetricFiresTrigger:
    """A missing metric should cause the trigger to fire (conservative)."""

    def setup_method(self) -> None:
        self.monitor = FalsificationMonitor(_make_config())

    def test_single_missing_metric(self) -> None:
        metrics = _healthy_metrics()
        del metrics["rolling_ic_60d"]
        results, diag = self.monitor.evaluate_all(metrics)
        f1 = next(r for r in results if r.trigger_id == "F1_signal_death")
        assert f1.passed is False
        assert diag.has_warnings

    def test_missing_metric_has_nan_value(self) -> None:
        metrics = _healthy_metrics()
        del metrics["max_drawdown"]
        results, _ = self.monitor.evaluate_all(metrics)
        f3 = next(r for r in results if r.trigger_id == "F3_excessive_drawdown")
        assert f3.passed is False
        import math

        assert math.isnan(f3.current_value)

    def test_all_missing_all_fire(self) -> None:
        results, diag = self.monitor.evaluate_all({})
        assert all(not r.passed for r in results)
        assert len(results) == 8


class TestF3DrawdownDirection:
    """F3 drawdown: more negative is worse. threshold=-0.25, healthy direction >=."""

    def setup_method(self) -> None:
        self.monitor = FalsificationMonitor(_make_config())

    def test_mild_drawdown_passes(self) -> None:
        """Drawdown of -5% is better than threshold of -25%."""
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = -0.05
        results, _ = self.monitor.evaluate_all(metrics)
        f3 = next(r for r in results if r.trigger_id == "F3_excessive_drawdown")
        assert f3.passed is True

    def test_exact_threshold_passes(self) -> None:
        """Exactly at -25% should pass (>= threshold)."""
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = -0.25
        results, _ = self.monitor.evaluate_all(metrics)
        f3 = next(r for r in results if r.trigger_id == "F3_excessive_drawdown")
        assert f3.passed is True

    def test_worse_than_threshold_fails(self) -> None:
        """Drawdown of -30% is worse than -25% threshold."""
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = -0.30
        results, _ = self.monitor.evaluate_all(metrics)
        f3 = next(r for r in results if r.trigger_id == "F3_excessive_drawdown")
        assert f3.passed is False

    def test_zero_drawdown_passes(self) -> None:
        """No drawdown (0.0) easily passes."""
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = 0.0
        results, _ = self.monitor.evaluate_all(metrics)
        f3 = next(r for r in results if r.trigger_id == "F3_excessive_drawdown")
        assert f3.passed is True


class TestF7BooleanRegimeAnomaly:
    """F7 boolean regime anomaly — threshold=false, value 0.0 means healthy."""

    def setup_method(self) -> None:
        self.monitor = FalsificationMonitor(_make_config())

    def test_healthy_zero_value(self) -> None:
        metrics = _healthy_metrics()
        metrics["benchmark_split_adjusted"] = 0.0
        results, _ = self.monitor.evaluate_all(metrics)
        f7 = next(r for r in results if r.trigger_id == "F7_regime_anomaly")
        assert f7.passed is True

    def test_anomaly_nonzero_value(self) -> None:
        metrics = _healthy_metrics()
        metrics["benchmark_split_adjusted"] = 1.0
        results, _ = self.monitor.evaluate_all(metrics)
        f7 = next(r for r in results if r.trigger_id == "F7_regime_anomaly")
        assert f7.passed is False

    def test_anomaly_large_nonzero(self) -> None:
        metrics = _healthy_metrics()
        metrics["benchmark_split_adjusted"] = 42.0
        results, _ = self.monitor.evaluate_all(metrics)
        f7 = next(r for r in results if r.trigger_id == "F7_regime_anomaly")
        assert f7.passed is False


class TestShouldHaltWithVeto:
    """should_halt returns True when any VETO trigger fires."""

    def setup_method(self) -> None:
        self.monitor = FalsificationMonitor(_make_config())

    def test_halt_with_single_veto(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = -0.30
        results, _ = self.monitor.evaluate_all(metrics)
        assert self.monitor.should_halt(results) is True

    def test_halt_with_multiple_vetos(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = -0.30
        metrics["rolling_ic_60d"] = 0.005
        results, _ = self.monitor.evaluate_all(metrics)
        assert self.monitor.should_halt(results) is True
        vetos = self.monitor.get_veto_triggers(results)
        assert len(vetos) == 2


class TestShouldHaltWithoutVeto:
    """should_halt returns False when only warnings fire."""

    def setup_method(self) -> None:
        self.monitor = FalsificationMonitor(_make_config())

    def test_no_halt_with_warnings_only(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_single_stock_weight"] = 0.20  # WARNING
        metrics["monthly_turnover_pct"] = 300  # WARNING
        results, _ = self.monitor.evaluate_all(metrics)
        assert self.monitor.should_halt(results) is False

    def test_no_halt_all_healthy(self) -> None:
        results, _ = self.monitor.evaluate_all(_healthy_metrics())
        assert self.monitor.should_halt(results) is False


class TestFrozenHashVerification:
    """verify_frozen_hash — SHA-256 config integrity."""

    def setup_method(self) -> None:
        self.monitor = FalsificationMonitor(_make_config())

    def test_hash_matches(self) -> None:
        content = b"triggers:\n  F1_signal_death:\n"
        expected = hashlib.sha256(content).hexdigest()
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(content)
            path = Path(f.name)
        try:
            ok, diag = self.monitor.verify_frozen_hash(path, expected)
            assert ok is True
        finally:
            path.unlink()

    def test_hash_mismatch(self) -> None:
        content = b"triggers: modified\n"
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(content)
            path = Path(f.name)
        try:
            ok, diag = self.monitor.verify_frozen_hash(path, "deadbeef")
            assert ok is False
            assert diag.has_warnings
        finally:
            path.unlink()

    def test_no_expected_hash_bootstraps(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(b"content\n")
            path = Path(f.name)
        try:
            ok, diag = self.monitor.verify_frozen_hash(path, None)
            assert ok is True
        finally:
            path.unlink()

    def test_missing_file_returns_false(self) -> None:
        fake_path = Path("/tmp/nonexistent_config_xyz.yaml")
        ok, diag = self.monitor.verify_frozen_hash(fake_path, "somehash")
        assert ok is False
        assert diag.has_errors


class TestGetVetoVsWarningSeparation:
    """get_veto_triggers and get_warning_triggers partition correctly."""

    def setup_method(self) -> None:
        self.monitor = FalsificationMonitor(_make_config())

    def test_separation_with_mixed_fires(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = -0.30  # VETO
        metrics["rolling_ic_60d"] = 0.005  # VETO
        metrics["max_single_stock_weight"] = 0.20  # WARNING
        metrics["monthly_turnover_pct"] = 300  # WARNING

        results, _ = self.monitor.evaluate_all(metrics)
        vetos = self.monitor.get_veto_triggers(results)
        warnings = self.monitor.get_warning_triggers(results)

        assert len(vetos) == 2
        assert len(warnings) == 2
        assert all(r.severity == Severity.VETO for r in vetos)
        assert all(r.severity == Severity.WARNING for r in warnings)

    def test_no_fires_empty_lists(self) -> None:
        results, _ = self.monitor.evaluate_all(_healthy_metrics())
        assert len(self.monitor.get_veto_triggers(results)) == 0
        assert len(self.monitor.get_warning_triggers(results)) == 0

    def test_veto_triggers_only_include_fired(self) -> None:
        """get_veto_triggers only returns triggers that actually fired."""
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = -0.30  # F3 fires
        # F1 and F2 remain healthy
        results, _ = self.monitor.evaluate_all(metrics)
        vetos = self.monitor.get_veto_triggers(results)
        assert len(vetos) == 1
        assert vetos[0].trigger_id == "F3_excessive_drawdown"
