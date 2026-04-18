"""Gate evaluation framework — G0 through G5 factor admission gates.

Each gate enforces a minimum quality threshold for a factor candidate.
ThresholdEvaluator is the reusable comparator; ``evaluate_factor_gates``
orchestrates G0-G5 evaluation for a single factor.

Gate definitions (default thresholds supplied via gate_config):
  G0 — OOS Sharpe            >= threshold  (e.g. 0.3)
  G1 — Permutation p-value   <  threshold  (e.g. 0.05)
  G2 — IC mean               >= threshold  (e.g. 0.02)
  G3 — IC IR                 >= threshold  (e.g. 0.5)
  G4 — Max drawdown          >= threshold  (e.g. -0.30, i.e. no worse than -30%)
  G5 — Marginal contribution >= threshold when combined with existing factors
"""

from __future__ import annotations

from nyse_core.contracts import Diagnostics, GateVerdict, ThresholdCheck


class ThresholdEvaluator:
    """Evaluate a single metric against a directional threshold.

    Stateless comparator reused across gates and falsification triggers.
    """

    _OPS = {
        ">=": lambda v, t: v >= t,
        ">": lambda v, t: v > t,
        "<": lambda v, t: v < t,
        "<=": lambda v, t: v <= t,
    }

    def evaluate(
        self,
        name: str,
        metric_name: str,
        value: float,
        threshold: float,
        direction: str,
    ) -> ThresholdCheck:
        """Compare *value* against *threshold* using *direction*.

        Parameters
        ----------
        name : str
            Human-readable check name (e.g. "G0").
        metric_name : str
            Name of the metric being tested (e.g. "oos_sharpe").
        value : float
            Current metric value.
        threshold : float
            Threshold to compare against.
        direction : str
            One of ">=", ">", "<", "<=".

        Returns
        -------
        ThresholdCheck
            Frozen dataclass with pass/fail result.

        Raises
        ------
        ValueError
            If *direction* is not a recognized operator.
        """
        if direction not in self._OPS:
            raise ValueError(f"Unknown direction '{direction}'. Must be one of {list(self._OPS)}")
        passed = bool(self._OPS[direction](value, threshold))
        return ThresholdCheck(
            name=name,
            metric_name=metric_name,
            current_value=value,
            threshold=threshold,
            direction=direction,
            passed=passed,
        )


# ── Default gate definitions ────────────────────────────────────────────────

DEFAULT_GATE_CONFIG: dict[str, dict] = {
    "G0": {"metric": "oos_sharpe", "threshold": 0.3, "direction": ">="},
    "G1": {"metric": "permutation_p", "threshold": 0.05, "direction": "<"},
    "G2": {"metric": "ic_mean", "threshold": 0.02, "direction": ">="},
    "G3": {"metric": "ic_ir", "threshold": 0.5, "direction": ">="},
    "G4": {"metric": "max_drawdown", "threshold": -0.30, "direction": ">="},
    "G5": {"metric": "marginal_contribution", "threshold": 0.0, "direction": ">"},
}


def evaluate_factor_gates(
    factor_metrics: dict[str, float],
    gate_config: dict | None = None,
    existing_factors: list[str] | None = None,
) -> tuple[GateVerdict, Diagnostics]:
    """Evaluate factor candidate through G0-G5 admission gates.

    Parameters
    ----------
    factor_metrics : dict[str, float]
        Metric values keyed by metric name (must include keys referenced by
        gate_config, e.g. "oos_sharpe", "permutation_p", "ic_mean", etc.).
    gate_config : dict | None
        Gate definitions. Each key is a gate name (e.g. "G0"), each value a
        dict with "metric", "threshold", "direction". Uses DEFAULT_GATE_CONFIG
        when None.
    existing_factors : list[str] | None
        Names of factors already in the portfolio. Informational — G5
        evaluation still relies on the ``marginal_contribution`` metric value
        being pre-computed and present in *factor_metrics*.

    Returns
    -------
    tuple[GateVerdict, Diagnostics]
        (verdict, diagnostics).
    """
    diag = Diagnostics()
    src = "gates.evaluate_factor_gates"
    config = gate_config or DEFAULT_GATE_CONFIG
    evaluator = ThresholdEvaluator()

    gate_results: dict[str, bool] = {}
    gate_metrics: dict[str, float] = {}

    for gate_name, gate_def in sorted(config.items()):
        metric_name = gate_def["metric"]
        threshold = gate_def["threshold"]
        direction = gate_def["direction"]

        if metric_name not in factor_metrics:
            diag.warning(
                src,
                f"Metric '{metric_name}' missing for gate {gate_name}; marking FAIL.",
                gate=gate_name,
            )
            gate_results[gate_name] = False
            gate_metrics[f"{gate_name}_value"] = float("nan")
            continue

        value = factor_metrics[metric_name]
        check = evaluator.evaluate(gate_name, metric_name, value, threshold, direction)
        gate_results[gate_name] = check.passed
        gate_metrics[f"{gate_name}_value"] = value

        level = "info" if check.passed else "warning"
        msg = (
            f"{gate_name} ({metric_name}): {value:.4f} {direction} {threshold} "
            f"-> {'PASS' if check.passed else 'FAIL'}"
        )
        getattr(diag, level)(src, msg, gate=gate_name)

    passed_all = all(gate_results.values()) if gate_results else False

    # Factor name extracted from metrics if present, else "unknown"
    factor_name = factor_metrics.get("factor_name", "unknown")
    if isinstance(factor_name, float):
        factor_name = "unknown"

    verdict = GateVerdict(
        factor_name=str(factor_name),
        gate_results=gate_results,
        gate_metrics=gate_metrics,
        passed_all=passed_all,
    )

    if existing_factors is not None:
        diag.info(
            src,
            f"Evaluated against {len(existing_factors)} existing factors.",
            existing=existing_factors,
        )

    return verdict, diag
