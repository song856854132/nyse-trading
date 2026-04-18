"""Dict-based multi-strategy registry with model comparison.

Manages multiple CombinationModel configurations and their backtest results,
enabling systematic comparison between Ridge, GBM, and Neural alternatives.

All functions are pure -- no I/O, no logging.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from nyse_core.contracts import Diagnostics

_MOD = "strategy_registry"


@dataclass(frozen=True)
class StrategyConfig:
    """Configuration for one strategy variant."""

    name: str
    model_type: str  # "ridge", "gbm", "neural"
    model_kwargs: dict[str, Any]
    top_n: int
    sell_buffer: float
    description: str


@dataclass(frozen=True)
class StrategyResult:
    """Backtest result for one strategy."""

    config: StrategyConfig
    oos_sharpe: float
    oos_cagr: float
    max_drawdown: float
    annual_turnover: float
    cost_drag_pct: float
    overfit_ratio: float  # in-sample Sharpe / OOS Sharpe


class StrategyRegistry:
    """Registry for managing strategy configurations and their results.

    Supports registration, backtest result recording, comparison across
    strategies, and selection of the best strategy with guardrails.
    """

    def __init__(self) -> None:
        self._strategies: dict[str, StrategyConfig] = {}
        self._results: dict[str, StrategyResult] = {}

    # ── Registration ────────────────────────────────────────────────────────

    def register(self, config: StrategyConfig) -> Diagnostics:
        """Register a strategy configuration.

        Parameters
        ----------
        config : StrategyConfig
            Strategy to register.

        Returns
        -------
        Diagnostics
        """
        diag = Diagnostics()
        src = f"{_MOD}.register"

        if config.name in self._strategies:
            diag.warning(
                src,
                f"Strategy '{config.name}' already registered; overwriting.",
            )

        self._strategies[config.name] = config
        diag.info(src, f"Registered strategy '{config.name}' ({config.model_type}).")
        return diag

    # ── Result Recording ────────────────────────────────────────────────────

    def record_result(self, name: str, result: StrategyResult) -> Diagnostics:
        """Record backtest results for a registered strategy.

        Parameters
        ----------
        name : str
            Strategy name (must be registered).
        result : StrategyResult
            Backtest result to record.

        Returns
        -------
        Diagnostics
        """
        diag = Diagnostics()
        src = f"{_MOD}.record_result"

        if name not in self._strategies:
            diag.error(
                src,
                f"Strategy '{name}' not registered. Register before recording results.",
            )
            return diag

        self._results[name] = result
        diag.info(
            src,
            f"Recorded results for '{name}': OOS Sharpe={result.oos_sharpe:.3f}, "
            f"overfit_ratio={result.overfit_ratio:.2f}.",
        )
        return diag

    # ── Comparison ──────────────────────────────────────────────────────────

    def compare(self) -> tuple[pd.DataFrame, Diagnostics]:
        """Return comparison DataFrame sorted by OOS Sharpe (descending).

        Columns: name, model_type, oos_sharpe, overfit_ratio, turnover,
                 cost_drag, max_dd.

        Returns
        -------
        tuple[pd.DataFrame, Diagnostics]
        """
        diag = Diagnostics()
        src = f"{_MOD}.compare"

        if not self._results:
            diag.warning(src, "No results recorded yet.")
            df = pd.DataFrame(
                columns=[
                    "name",
                    "model_type",
                    "oos_sharpe",
                    "overfit_ratio",
                    "turnover",
                    "cost_drag",
                    "max_dd",
                ]
            )
            return df, diag

        rows: list[dict[str, Any]] = []
        for name, result in self._results.items():
            rows.append(
                {
                    "name": name,
                    "model_type": result.config.model_type,
                    "oos_sharpe": result.oos_sharpe,
                    "overfit_ratio": result.overfit_ratio,
                    "turnover": result.annual_turnover,
                    "cost_drag": result.cost_drag_pct,
                    "max_dd": result.max_drawdown,
                }
            )

        df = pd.DataFrame(rows).sort_values("oos_sharpe", ascending=False)
        df = df.reset_index(drop=True)

        diag.info(src, f"Compared {len(rows)} strategies.")
        return df, diag

    # ── Selection ───────────────────────────────────────────────────────────

    def select_best(
        self,
        min_sharpe_improvement: float = 0.1,
        max_overfit_ratio: float = 3.0,
        baseline: str = "ridge_default",
    ) -> tuple[str | None, Diagnostics]:
        """Select best strategy with guardrails.

        An alternative strategy must:
          1. Beat baseline by at least min_sharpe_improvement in OOS Sharpe
          2. Have overfit_ratio < max_overfit_ratio

        If no alternative beats the baseline, returns None (stick with Ridge).
        This implements the plan rule: GBM/Neural must beat Ridge by >0.1
        Sharpe OOS to adopt.

        Parameters
        ----------
        min_sharpe_improvement : float
            Minimum OOS Sharpe improvement over baseline.
        max_overfit_ratio : float
            Maximum acceptable overfit ratio.
        baseline : str
            Name of the baseline strategy.

        Returns
        -------
        tuple[str | None, Diagnostics]
            (name of best strategy or None, diagnostics)
        """
        diag = Diagnostics()
        src = f"{_MOD}.select_best"

        if baseline not in self._results:
            diag.warning(src, f"Baseline '{baseline}' has no results recorded.")
            # If no baseline, can't compare -- return top strategy if it passes overfit
            if not self._results:
                diag.warning(src, "No results to select from.")
                return None, diag

            # Without baseline, pick the best that passes overfit check
            candidates = [
                (name, r) for name, r in self._results.items() if r.overfit_ratio < max_overfit_ratio
            ]
            if not candidates:
                diag.info(src, "All strategies exceed overfit ratio threshold.")
                return None, diag

            best_name = max(candidates, key=lambda x: x[1].oos_sharpe)[0]
            diag.info(
                src,
                f"No baseline found; selected '{best_name}' as best passing overfit check.",
            )
            return best_name, diag

        baseline_sharpe = self._results[baseline].oos_sharpe

        best_candidate: str | None = None
        best_sharpe = baseline_sharpe

        for name, result in self._results.items():
            if name == baseline:
                continue

            # Check overfit guardrail
            if result.overfit_ratio >= max_overfit_ratio:
                diag.info(
                    src,
                    f"Strategy '{name}' rejected: overfit_ratio={result.overfit_ratio:.2f} "
                    f">= {max_overfit_ratio}.",
                )
                continue

            # Check minimum improvement
            improvement = result.oos_sharpe - baseline_sharpe
            if improvement < min_sharpe_improvement:
                diag.info(
                    src,
                    f"Strategy '{name}': improvement={improvement:.3f} < required {min_sharpe_improvement}.",
                )
                continue

            # Candidate passes all guardrails
            if result.oos_sharpe > best_sharpe:
                best_sharpe = result.oos_sharpe
                best_candidate = name

        if best_candidate is None:
            diag.info(
                src,
                f"No alternative beats baseline '{baseline}' "
                f"(Sharpe={baseline_sharpe:.3f}) by >= {min_sharpe_improvement}. "
                f"Sticking with baseline.",
            )
        else:
            diag.info(
                src,
                f"Selected '{best_candidate}' (Sharpe={best_sharpe:.3f}) "
                f"over baseline '{baseline}' (Sharpe={baseline_sharpe:.3f}).",
            )

        return best_candidate, diag

    # ── Accessors ───────────────────────────────────────────────────────────

    def get_all(self) -> dict[str, StrategyConfig]:
        """Return all registered strategies."""
        return dict(self._strategies)
