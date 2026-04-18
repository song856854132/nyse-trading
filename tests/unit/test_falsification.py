"""Unit tests for FalsificationMonitor (F1-F8 triggers)."""

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
        "benchmark_split_adjusted": 0.0,  # false → 0.0 means healthy
        "max_feature_staleness_days": 3,
    }


# ── Tests ───────────────────────────────────────────────────────────────────


class TestFalsificationMonitor:
    def setup_method(self) -> None:
        self.config = _make_config()
        self.monitor = FalsificationMonitor(self.config)

    # -- VETO triggers -------------------------------------------------------

    def test_veto_fires_on_excessive_drawdown(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = -0.30  # breaches -0.25
        results, _ = self.monitor.evaluate_all(metrics)
        f3 = [r for r in results if r.trigger_id == "F3_excessive_drawdown"][0]
        assert f3.passed is False
        assert f3.severity == Severity.VETO

    def test_veto_fires_on_signal_death(self) -> None:
        metrics = _healthy_metrics()
        metrics["rolling_ic_60d"] = 0.005  # below 0.01
        results, _ = self.monitor.evaluate_all(metrics)
        f1 = [r for r in results if r.trigger_id == "F1_signal_death"][0]
        assert f1.passed is False
        assert f1.severity == Severity.VETO

    def test_veto_fires_on_factor_death(self) -> None:
        metrics = _healthy_metrics()
        metrics["core_factor_sign_flips"] = 5  # exceeds 3
        results, _ = self.monitor.evaluate_all(metrics)
        f2 = [r for r in results if r.trigger_id == "F2_factor_death"][0]
        assert f2.passed is False

    # -- WARNING triggers ----------------------------------------------------

    def test_warning_fires_on_concentration(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_single_stock_weight"] = 0.20  # exceeds 0.15
        results, _ = self.monitor.evaluate_all(metrics)
        f4 = [r for r in results if r.trigger_id == "F4_concentration"][0]
        assert f4.passed is False
        assert f4.severity == Severity.WARNING

    def test_warning_fires_on_turnover_spike(self) -> None:
        metrics = _healthy_metrics()
        metrics["monthly_turnover_pct"] = 300  # exceeds 200
        results, _ = self.monitor.evaluate_all(metrics)
        f5 = [r for r in results if r.trigger_id == "F5_turnover_spike"][0]
        assert f5.passed is False
        assert f5.severity == Severity.WARNING

    # -- No false positives --------------------------------------------------

    def test_no_false_positives_healthy_metrics(self) -> None:
        results, diag = self.monitor.evaluate_all(_healthy_metrics())
        assert all(r.passed for r in results), [r.trigger_id for r in results if not r.passed]
        assert not diag.has_errors

    # -- Frozen hash ---------------------------------------------------------

    def test_verify_frozen_hash_matches(self) -> None:
        content = b"frozen: true\n"
        expected = hashlib.sha256(content).hexdigest()
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(content)
            path = Path(f.name)
        try:
            ok, diag = self.monitor.verify_frozen_hash(path, expected)
            assert ok is True
            assert not diag.has_errors
        finally:
            path.unlink()

    def test_verify_frozen_hash_mismatch(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(b"modified content\n")
            path = Path(f.name)
        try:
            ok, diag = self.monitor.verify_frozen_hash(path, "0000dead")
            assert ok is False
            assert diag.has_warnings
        finally:
            path.unlink()

    def test_verify_frozen_hash_no_expected(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(b"content\n")
            path = Path(f.name)
        try:
            ok, diag = self.monitor.verify_frozen_hash(path, None)
            assert ok is True
        finally:
            path.unlink()

    # -- should_halt ---------------------------------------------------------

    def test_should_halt_when_veto_fires(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = -0.30
        results, _ = self.monitor.evaluate_all(metrics)
        assert self.monitor.should_halt(results) is True

    def test_should_not_halt_when_only_warning(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_single_stock_weight"] = 0.20  # WARNING only
        results, _ = self.monitor.evaluate_all(metrics)
        assert self.monitor.should_halt(results) is False

    # -- evaluate_all returns correct count ----------------------------------

    def test_evaluate_all_returns_8_results(self) -> None:
        results, _ = self.monitor.evaluate_all(_healthy_metrics())
        assert len(results) == 8

    # -- Boolean trigger (F7) ------------------------------------------------

    def test_boolean_trigger_f7_fires(self) -> None:
        metrics = _healthy_metrics()
        metrics["benchmark_split_adjusted"] = 1.0  # not 0 → fires
        results, _ = self.monitor.evaluate_all(metrics)
        f7 = [r for r in results if r.trigger_id == "F7_regime_anomaly"][0]
        assert f7.passed is False

    def test_boolean_trigger_f7_healthy(self) -> None:
        metrics = _healthy_metrics()
        metrics["benchmark_split_adjusted"] = 0.0  # false → healthy
        results, _ = self.monitor.evaluate_all(metrics)
        f7 = [r for r in results if r.trigger_id == "F7_regime_anomaly"][0]
        assert f7.passed is True

    # -- Empty metrics -------------------------------------------------------

    def test_empty_metrics_all_fire(self) -> None:
        results, diag = self.monitor.evaluate_all({})
        assert all(not r.passed for r in results)
        assert diag.has_warnings

    # -- Multiple simultaneous fires -----------------------------------------

    def test_multiple_triggers_fire(self) -> None:
        metrics = _healthy_metrics()
        metrics["max_drawdown"] = -0.30  # VETO
        metrics["max_single_stock_weight"] = 0.20  # WARNING
        metrics["monthly_turnover_pct"] = 300  # WARNING
        results, _ = self.monitor.evaluate_all(metrics)
        fired = [r for r in results if not r.passed]
        assert len(fired) == 3
        vetos = self.monitor.get_veto_triggers(results)
        warnings = self.monitor.get_warning_triggers(results)
        assert len(vetos) == 1
        assert len(warnings) == 2
