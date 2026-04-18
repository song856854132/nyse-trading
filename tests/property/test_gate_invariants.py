"""Property tests for gate evaluation invariants.

CONTRACT:
- ThresholdEvaluator correctly applies directional comparisons
- All gates pass when all metrics exceed thresholds
- Any single gate failure prevents passed_all=True
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from nyse_core.gates import (
    DEFAULT_GATE_CONFIG,
    ThresholdEvaluator,
    evaluate_factor_gates,
)

# ── Property: ThresholdEvaluator correctness ─────────────────────────────────


class TestThresholdEvaluatorCorrect:
    """ThresholdEvaluator must correctly evaluate directional comparisons."""

    @pytest.mark.property
    @given(
        value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        threshold=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_threshold_evaluator_correct(self, value: float, threshold: float) -> None:
        """value >= threshold with direction '>=' must return True iff value >= threshold."""
        evaluator = ThresholdEvaluator()
        result = evaluator.evaluate("test", "metric", value, threshold, ">=")
        assert result.passed == (value >= threshold), (
            f"Expected {value} >= {threshold} to be {value >= threshold}, got {result.passed}"
        )

    @pytest.mark.property
    @given(
        value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        threshold=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_threshold_evaluator_inverse(self, value: float, threshold: float) -> None:
        """value < threshold with direction '>=' must return False."""
        evaluator = ThresholdEvaluator()
        assume(value < threshold)
        result = evaluator.evaluate("test", "metric", value, threshold, ">=")
        assert result.passed is False, f"Expected {value} >= {threshold} to fail, but it passed"

    @pytest.mark.property
    @given(
        value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        threshold=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_gt_direction(self, value: float, threshold: float) -> None:
        """Strictly greater-than direction."""
        evaluator = ThresholdEvaluator()
        result = evaluator.evaluate("test", "metric", value, threshold, ">")
        assert result.passed == (value > threshold)

    @pytest.mark.property
    @given(
        value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        threshold=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_lt_direction(self, value: float, threshold: float) -> None:
        """Strictly less-than direction."""
        evaluator = ThresholdEvaluator()
        result = evaluator.evaluate("test", "metric", value, threshold, "<")
        assert result.passed == (value < threshold)

    @pytest.mark.property
    @given(
        value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        threshold=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_le_direction(self, value: float, threshold: float) -> None:
        """Less-than-or-equal direction."""
        evaluator = ThresholdEvaluator()
        result = evaluator.evaluate("test", "metric", value, threshold, "<=")
        assert result.passed == (value <= threshold)


# ── Property: all gates pass when metrics are excellent ──────────────────────


class TestAllGatesPassWhenExcellent:
    """When all metrics are well above thresholds, passed_all must be True."""

    @pytest.mark.property
    @given(
        sharpe_extra=st.floats(min_value=0.01, max_value=5.0),
        ic_mean_extra=st.floats(min_value=0.001, max_value=0.5),
        ic_ir_extra=st.floats(min_value=0.01, max_value=5.0),
        marginal_extra=st.floats(min_value=0.001, max_value=1.0),
    )
    @settings(max_examples=100, deadline=None)
    def test_all_gates_pass_when_metrics_excellent(
        self,
        sharpe_extra: float,
        ic_mean_extra: float,
        ic_ir_extra: float,
        marginal_extra: float,
    ) -> None:
        """All metrics well above thresholds -> passed_all=True."""
        factor_metrics = {
            "oos_sharpe": 0.3 + sharpe_extra,
            "permutation_p": 0.05 - 0.04,  # well below 0.05
            "ic_mean": 0.02 + ic_mean_extra,
            "ic_ir": 0.5 + ic_ir_extra,
            "max_drawdown": -0.30 + 0.10,  # -0.20, better than -0.30
            "marginal_contribution": 0.0 + marginal_extra,
        }

        verdict, _diag = evaluate_factor_gates(factor_metrics)
        assert verdict.passed_all is True, (
            f"Expected all gates to pass with excellent metrics, but got gate_results={verdict.gate_results}"
        )


# ── Property: any gate fail prevents pass_all ────────────────────────────────


class TestAnyGateFailPreventsPassAll:
    """If any single gate fails, passed_all must be False."""

    @pytest.mark.property
    @given(gate_to_fail=st.sampled_from(list(DEFAULT_GATE_CONFIG.keys())))
    @settings(max_examples=100, deadline=None)
    def test_any_gate_fail_prevents_pass_all(self, gate_to_fail: str) -> None:
        """One metric below threshold -> passed_all=False."""
        # Start with all-passing metrics
        factor_metrics = {
            "oos_sharpe": 1.0,
            "permutation_p": 0.01,
            "ic_mean": 0.10,
            "ic_ir": 2.0,
            "max_drawdown": -0.05,
            "marginal_contribution": 0.5,
        }

        # Sabotage the selected gate
        gate_def = DEFAULT_GATE_CONFIG[gate_to_fail]
        metric_name = gate_def["metric"]
        threshold = gate_def["threshold"]
        direction = gate_def["direction"]

        if direction in (">=", ">"):
            # Set value well below threshold
            factor_metrics[metric_name] = threshold - 1.0
        else:
            # direction is "<" or "<="
            # Set value well above threshold
            factor_metrics[metric_name] = threshold + 1.0

        verdict, _diag = evaluate_factor_gates(factor_metrics)
        assert verdict.passed_all is False, (
            f"Expected passed_all=False when gate {gate_to_fail} is failed, "
            f"but got passed_all=True. gate_results={verdict.gate_results}"
        )
