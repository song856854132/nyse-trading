"""Evaluate F1-F8 pre-registered falsification triggers.

All triggers are defined in ``config/falsification_triggers.yaml`` and frozen
before the first live trade.  The ``FalsificationMonitor`` checks current
metric values against those thresholds using the shared ``ThresholdEvaluator``.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from nyse_core.contracts import Diagnostics, FalsificationCheckResult
from nyse_core.gates import ThresholdEvaluator
from nyse_core.schema import Severity

if TYPE_CHECKING:
    from pathlib import Path

    from nyse_core.config_schema import FalsificationTriggersConfig, TriggerConfig

_SRC = "monitoring.falsification"

# Mapping from trigger-id to the ThresholdEvaluator direction that represents
# a *healthy* reading.  When the check *fails* (passed=False), the trigger
# has fired.
#
# Most thresholds represent an upper bound on a "bad" metric, so the healthy
# direction is "<=".  Exceptions:
#   F3 (max_drawdown): more negative is worse, so healthy means value >= threshold
#   F7 (benchmark_split_adjusted): boolean equality check, handled separately

_HEALTHY_DIRECTION: dict[str, str] = {
    "F1_signal_death": ">=",  # rolling IC must stay >= 0.01
    "F2_factor_death": "<=",  # sign flips must stay <= 3
    "F3_excessive_drawdown": ">=",  # drawdown must stay >= -0.25 (less negative)
    "F4_concentration": "<=",  # weight must stay <= 0.15
    "F5_turnover_spike": "<=",  # turnover must stay <= 200
    "F6_cost_drag": "<=",  # cost drag must stay <= 5.0
    "F7_regime_anomaly": "<=",  # boolean; special-cased below
    "F8_data_staleness": "<=",  # staleness days must stay <= 10
}


class FalsificationMonitor:
    """Evaluate F1-F8 pre-registered falsification triggers."""

    def __init__(self, config: FalsificationTriggersConfig) -> None:
        self._config = config
        self._evaluator = ThresholdEvaluator()

    # ── Frozen-config integrity ─────────────────────────────────────────────

    def verify_frozen_hash(
        self,
        config_path: Path,
        expected_hash: str | None = None,
    ) -> tuple[bool, Diagnostics]:
        """Compute SHA-256 of *config_path* and compare against *expected_hash*.

        If *expected_hash* is ``None`` the method computes and logs the hash
        but always returns ``(True, diag)`` so callers can bootstrap the
        first hash without failing.
        """
        diag = Diagnostics()
        try:
            raw = config_path.read_bytes()
        except OSError as exc:
            diag.error(_SRC, f"Cannot read config file: {exc}", path=str(config_path))
            return False, diag

        file_hash = hashlib.sha256(raw).hexdigest()
        diag.info(_SRC, f"Config hash: {file_hash}", path=str(config_path))

        if expected_hash is None:
            diag.info(_SRC, "No expected hash provided; returning computed hash only.")
            return True, diag

        if file_hash != expected_hash:
            diag.warning(
                _SRC,
                f"Config file modified after frozen_date ({self._config.frozen_date}). "
                f"Expected {expected_hash}, got {file_hash}.",
            )
            return False, diag

        diag.info(_SRC, "Config hash matches expected value.")
        return True, diag

    # ── Trigger evaluation ──────────────────────────────────────────────────

    def evaluate_all(
        self,
        current_metrics: dict[str, float],
    ) -> tuple[list[FalsificationCheckResult], Diagnostics]:
        """Evaluate all triggers against *current_metrics*.

        Returns a list of :class:`FalsificationCheckResult` (one per trigger)
        and aggregated diagnostics.
        """
        diag = Diagnostics()
        results: list[FalsificationCheckResult] = []

        for trigger_id, trigger_cfg in self._config.triggers.items():
            result = self._evaluate_single(trigger_id, trigger_cfg, current_metrics, diag)
            results.append(result)

        fired = [r for r in results if not r.passed]
        diag.info(
            _SRC,
            f"Evaluated {len(results)} triggers; {len(fired)} fired.",
        )
        return results, diag

    def _evaluate_single(
        self,
        trigger_id: str,
        cfg: TriggerConfig,
        current_metrics: dict[str, float],
        diag: Diagnostics,
    ) -> FalsificationCheckResult:
        """Evaluate one trigger and return a :class:`FalsificationCheckResult`."""
        severity = Severity.VETO if cfg.severity == "VETO" else Severity.WARNING
        metric = cfg.metric

        if metric not in current_metrics:
            diag.warning(
                _SRC,
                f"Metric '{metric}' missing for {trigger_id}; treating as FIRED.",
                trigger=trigger_id,
            )
            return FalsificationCheckResult(
                trigger_id=trigger_id,
                trigger_name=cfg.description or trigger_id,
                current_value=float("nan"),
                threshold=float(cfg.threshold) if not isinstance(cfg.threshold, bool) else 0.0,
                severity=severity,
                passed=False,
                description=f"Metric '{metric}' not provided.",
            )

        value = current_metrics[metric]

        # F7 is a boolean equality check
        if isinstance(cfg.threshold, bool):
            passed = (value != 0.0) == cfg.threshold if cfg.threshold else value == 0.0
            # Simpler: threshold=false means value should be 0 (false-y) to be healthy
            passed = bool(value == 0.0) if not cfg.threshold else bool(value != 0.0)
            return FalsificationCheckResult(
                trigger_id=trigger_id,
                trigger_name=cfg.description or trigger_id,
                current_value=value,
                threshold=0.0,
                severity=severity,
                passed=passed,
                description=cfg.description or trigger_id,
            )

        threshold = float(cfg.threshold)
        direction = _HEALTHY_DIRECTION.get(trigger_id, "<=")

        check = self._evaluator.evaluate(
            name=trigger_id,
            metric_name=metric,
            value=value,
            threshold=threshold,
            direction=direction,
        )

        passed = check.passed
        level = "info" if passed else "warning"
        getattr(diag, level)(
            _SRC,
            f"{trigger_id}: {metric}={value} {direction} {threshold} -> {'OK' if passed else 'FIRED'}",
            trigger=trigger_id,
            severity=cfg.severity,
        )

        return FalsificationCheckResult(
            trigger_id=trigger_id,
            trigger_name=cfg.description or trigger_id,
            current_value=value,
            threshold=threshold,
            severity=severity,
            passed=passed,
            description=cfg.description or trigger_id,
        )

    # ── Convenience filters ─────────────────────────────────────────────────

    def get_veto_triggers(
        self,
        results: list[FalsificationCheckResult],
    ) -> list[FalsificationCheckResult]:
        """Return VETO-severity triggers that fired (passed=False)."""
        return [r for r in results if r.severity == Severity.VETO and not r.passed]

    def get_warning_triggers(
        self,
        results: list[FalsificationCheckResult],
    ) -> list[FalsificationCheckResult]:
        """Return WARNING-severity triggers that fired (passed=False)."""
        return [r for r in results if r.severity == Severity.WARNING and not r.passed]

    def should_halt(self, results: list[FalsificationCheckResult]) -> bool:
        """Return ``True`` if any VETO-severity trigger has fired."""
        return len(self.get_veto_triggers(results)) > 0
