"""Unit tests for ThresholdEvaluator and G0-G5 gate evaluation."""

from __future__ import annotations

import pytest

from nyse_core.contracts import GateVerdict, ThresholdCheck
from nyse_core.gates import (
    ThresholdEvaluator,
    evaluate_factor_gates,
)

# ── ThresholdEvaluator ───────────────────────────────────────────────────────


class TestThresholdEvaluator:
    def setup_method(self):
        self.ev = ThresholdEvaluator()

    def test_gte_pass(self):
        check = self.ev.evaluate("G0", "sharpe", 0.5, 0.3, ">=")
        assert check.passed is True
        assert check.current_value == 0.5

    def test_gte_fail(self):
        check = self.ev.evaluate("G0", "sharpe", 0.2, 0.3, ">=")
        assert check.passed is False

    def test_gte_boundary(self):
        check = self.ev.evaluate("G0", "sharpe", 0.3, 0.3, ">=")
        assert check.passed is True

    def test_gt_pass(self):
        check = self.ev.evaluate("G5", "contrib", 0.01, 0.0, ">")
        assert check.passed is True

    def test_gt_fail_at_boundary(self):
        check = self.ev.evaluate("G5", "contrib", 0.0, 0.0, ">")
        assert check.passed is False

    def test_lt_pass(self):
        check = self.ev.evaluate("G1", "p_value", 0.01, 0.05, "<")
        assert check.passed is True

    def test_lt_fail(self):
        check = self.ev.evaluate("G1", "p_value", 0.10, 0.05, "<")
        assert check.passed is False

    def test_lte_pass(self):
        check = self.ev.evaluate("test", "metric", 0.05, 0.05, "<=")
        assert check.passed is True

    def test_lte_fail(self):
        check = self.ev.evaluate("test", "metric", 0.06, 0.05, "<=")
        assert check.passed is False

    def test_unknown_direction_raises(self):
        with pytest.raises(ValueError, match="Unknown direction"):
            self.ev.evaluate("test", "metric", 0.5, 0.3, "==")

    def test_returns_threshold_check_type(self):
        check = self.ev.evaluate("G0", "sharpe", 0.5, 0.3, ">=")
        assert isinstance(check, ThresholdCheck)
        assert check.name == "G0"
        assert check.metric_name == "sharpe"
        assert check.direction == ">="
        assert check.threshold == 0.3


# ── evaluate_factor_gates (G0-G5) ───────────────────────────────────────────


class TestEvaluateFactorGates:
    def _all_passing_metrics(self) -> dict[str, float]:
        """Metrics that pass all default gates."""
        return {
            "oos_sharpe": 0.8,
            "permutation_p": 0.01,
            "ic_mean": 0.05,
            "ic_ir": 1.0,
            "max_drawdown": -0.15,
            "marginal_contribution": 0.02,
        }

    def test_all_gates_pass(self):
        metrics = self._all_passing_metrics()
        verdict, diag = evaluate_factor_gates(metrics)
        assert isinstance(verdict, GateVerdict)
        assert verdict.passed_all is True
        assert all(verdict.gate_results.values())
        assert not diag.has_errors

    def test_g0_sharpe_fail(self):
        metrics = self._all_passing_metrics()
        metrics["oos_sharpe"] = 0.1  # below 0.3
        verdict, _ = evaluate_factor_gates(metrics)
        assert verdict.gate_results["G0"] is False
        assert verdict.passed_all is False

    def test_g1_pvalue_fail(self):
        metrics = self._all_passing_metrics()
        metrics["permutation_p"] = 0.10  # above 0.05
        verdict, _ = evaluate_factor_gates(metrics)
        assert verdict.gate_results["G1"] is False

    def test_g2_ic_mean_fail(self):
        metrics = self._all_passing_metrics()
        metrics["ic_mean"] = 0.005  # below 0.02
        verdict, _ = evaluate_factor_gates(metrics)
        assert verdict.gate_results["G2"] is False

    def test_g3_ic_ir_fail(self):
        metrics = self._all_passing_metrics()
        metrics["ic_ir"] = 0.3  # below 0.5
        verdict, _ = evaluate_factor_gates(metrics)
        assert verdict.gate_results["G3"] is False

    def test_g4_maxdd_fail(self):
        metrics = self._all_passing_metrics()
        metrics["max_drawdown"] = -0.50  # worse than -0.30
        verdict, _ = evaluate_factor_gates(metrics)
        assert verdict.gate_results["G4"] is False

    def test_g5_marginal_fail(self):
        metrics = self._all_passing_metrics()
        metrics["marginal_contribution"] = -0.01  # not > 0
        verdict, _ = evaluate_factor_gates(metrics)
        assert verdict.gate_results["G5"] is False

    def test_missing_metric_fails_gate(self):
        metrics = {"oos_sharpe": 0.8}  # missing others
        verdict, diag = evaluate_factor_gates(metrics)
        assert verdict.passed_all is False
        assert diag.has_warnings

    def test_custom_gate_config(self):
        config = {
            "G0": {"metric": "oos_sharpe", "threshold": 1.0, "direction": ">="},
        }
        metrics = {"oos_sharpe": 0.8}
        verdict, _ = evaluate_factor_gates(metrics, gate_config=config)
        assert verdict.gate_results["G0"] is False

    def test_existing_factors_info(self):
        metrics = self._all_passing_metrics()
        _, diag = evaluate_factor_gates(metrics, existing_factors=["momentum", "value"])
        info_msgs = [m for m in diag.messages if "existing" in m.message.lower()]
        assert len(info_msgs) > 0

    def test_gate_metrics_populated(self):
        metrics = self._all_passing_metrics()
        verdict, _ = evaluate_factor_gates(metrics)
        assert "G0_value" in verdict.gate_metrics
        assert verdict.gate_metrics["G0_value"] == 0.8
