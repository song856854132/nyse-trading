"""Rolling IC monitoring and retrain-trigger detection.

Tracks whether each factor's information coefficient has drifted below
the acceptable threshold over a rolling window, and whether the IC
trend is downward (negative slope), which together signal the need
to retrain the combination model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from nyse_core.contracts import Diagnostics, DriftCheckResult

if TYPE_CHECKING:
    import pandas as pd

_SRC = "monitoring.drift_monitor"


class DriftMonitor:
    """Rolling IC monitoring + retrain trigger detection."""

    def __init__(
        self,
        ic_threshold: float = 0.015,
        window_days: int = 60,
    ) -> None:
        self._ic_threshold = ic_threshold
        self._window_days = window_days

    # ── Single factor ───────────────────────────────────────────────────────

    def check_factor_drift(
        self,
        factor_name: str,
        ic_series: pd.Series,
    ) -> tuple[DriftCheckResult, Diagnostics]:
        """Check if *factor_name*'s rolling IC has drifted below threshold.

        Uses the last ``window_days`` values from *ic_series*.

        Returns
        -------
        tuple[DriftCheckResult, Diagnostics]
        """
        diag = Diagnostics()

        if ic_series is None or len(ic_series) == 0:
            diag.warning(_SRC, f"No IC data for factor '{factor_name}'.")
            return DriftCheckResult(
                factor_name=factor_name,
                rolling_ic=float("nan"),
                drift_detected=True,
                retrain_recommended=True,
                ic_threshold=self._ic_threshold,
            ), diag

        window = ic_series.tail(self._window_days).dropna()
        if len(window) == 0:
            diag.warning(_SRC, f"All IC values NaN for factor '{factor_name}'.")
            return DriftCheckResult(
                factor_name=factor_name,
                rolling_ic=float("nan"),
                drift_detected=True,
                retrain_recommended=True,
                ic_threshold=self._ic_threshold,
            ), diag

        mean_ic = float(window.mean())
        drift_detected = mean_ic < self._ic_threshold

        # Retrain = drift AND downward slope (linear regression over the window)
        retrain_recommended = False
        if drift_detected and len(window) >= 2:
            x = np.arange(len(window), dtype=float)
            y = window.values.astype(float)
            slope = float(np.polyfit(x, y, 1)[0])
            retrain_recommended = slope < 0.0

        level = "info" if not drift_detected else "warning"
        getattr(diag, level)(
            _SRC,
            f"Factor '{factor_name}': mean_ic={mean_ic:.4f}, "
            f"threshold={self._ic_threshold}, drift={drift_detected}, "
            f"retrain={retrain_recommended}",
            factor=factor_name,
        )

        return DriftCheckResult(
            factor_name=factor_name,
            rolling_ic=mean_ic,
            drift_detected=drift_detected,
            retrain_recommended=retrain_recommended,
            ic_threshold=self._ic_threshold,
        ), diag

    # ── All factors ─────────────────────────────────────────────────────────

    def check_all_factors(
        self,
        ic_history: dict[str, pd.Series],
    ) -> tuple[list[DriftCheckResult], Diagnostics]:
        """Check all factors in *ic_history* and return aggregated results."""
        diag = Diagnostics()
        results: list[DriftCheckResult] = []

        for factor_name, ic_series in ic_history.items():
            result, factor_diag = self.check_factor_drift(factor_name, ic_series)
            results.append(result)
            diag.merge(factor_diag)

        drifted = sum(1 for r in results if r.drift_detected)
        diag.info(
            _SRC,
            f"Checked {len(results)} factors; {drifted} drifting.",
        )
        return results, diag

    # ── Aggregation ─────────────────────────────────────────────────────────

    def should_retrain(self, results: list[DriftCheckResult]) -> bool:
        """Return ``True`` if any factor recommends retraining."""
        return any(r.retrain_recommended for r in results)
