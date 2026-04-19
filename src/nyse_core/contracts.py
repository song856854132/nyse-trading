"""Frozen dataclass data contracts for inter-module communication.

All data flowing between nyse_core modules passes through these contracts.
All nyse_core public functions return (result, Diagnostics) tuples.

ARCHITECTURE:
  UniverseSnapshot → FeatureMatrix → CompositeScore → TradePlan
       ↕                  ↕                               ↕
  GateVerdict      BacktestResult              PortfolioBuildResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum, unique
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from datetime import datetime

    from nyse_core.schema import RegimeState, Severity, Side


# ── Holdout leakage guard (iron rule 1) ───────────────────────────────────────
#
# Research period:  up to and including 2023-12-31.
# Holdout period:   2024-01-01 through 2025-12-31 (reserved for one-shot test).
#
# Any nyse_core function that accepts a date, date range, or date-bearing
# DataFrame/Index must route boundary dates through ``reject_holdout_dates``.
# A boundary strictly greater than ``HOLDOUT_BOUNDARY`` raises
# ``HoldoutLeakageError`` immediately — before any data is read or computed on.

HOLDOUT_BOUNDARY: date = date(2023, 12, 31)


class HoldoutLeakageError(ValueError):
    """Raised when a nyse_core entrypoint is asked to touch holdout dates.

    Iron rule 1 from ``docs/RALPH_LOOP_TASK.md``: no read, query, or backtest
    on any date after 2023-12-31. Holdout (2024-01-01 → 2025-12-31) is a
    one-shot evaluation reserved for the final pre-deployment gate.
    """


def reject_holdout_dates(
    *candidates: date | pd.Timestamp | pd.DatetimeIndex | pd.Series | None,
    source: str,
) -> None:
    """Raise ``HoldoutLeakageError`` if any candidate exceeds ``HOLDOUT_BOUNDARY``.

    Accepts a heterogeneous mix of scalar dates, ``pd.Timestamp``, pandas
    ``DatetimeIndex``, or ``pd.Series`` of datetimes. ``None`` is skipped so
    callers can forward optional parameters directly.

    Parameters
    ----------
    *candidates
        Dates or date containers to validate.
    source
        Caller identifier (e.g. ``"pit.enforce_pit_lags"``) — surfaced in the
        error message to make debugging unambiguous.

    Raises
    ------
    HoldoutLeakageError
        If any normalized date is strictly greater than ``HOLDOUT_BOUNDARY``.
    """
    boundary_ts = pd.Timestamp(HOLDOUT_BOUNDARY)
    for candidate in candidates:
        if candidate is None:
            continue

        if isinstance(candidate, (pd.DatetimeIndex, pd.Series)):
            if len(candidate) == 0:
                continue
            stamps = pd.to_datetime(candidate, errors="coerce").dropna()
            if len(stamps) == 0:
                continue
            max_ts = stamps.max()
        else:
            max_ts = pd.Timestamp(candidate)

        if pd.isna(max_ts):
            continue

        if max_ts > boundary_ts:
            offending = max_ts.date().isoformat()
            raise HoldoutLeakageError(
                f"{source}: refuses to process date {offending}; holdout boundary "
                f"is {HOLDOUT_BOUNDARY.isoformat()} (iron rule 1)."
            )


# ── Diagnostics (returned by ALL nyse_core public functions) ──────────────────


@unique
class DiagLevel(StrEnum):
    """Diagnostic message severity."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class DiagMessage:
    """Single diagnostic message from a nyse_core function."""

    level: DiagLevel
    source: str  # module.function that produced this message
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Diagnostics:
    """Collection of diagnostic messages. Mutable — functions append to it."""

    messages: list[DiagMessage] = field(default_factory=list)

    def debug(self, source: str, message: str, **ctx: Any) -> None:
        self.messages.append(DiagMessage(DiagLevel.DEBUG, source, message, ctx))

    def info(self, source: str, message: str, **ctx: Any) -> None:
        self.messages.append(DiagMessage(DiagLevel.INFO, source, message, ctx))

    def warning(self, source: str, message: str, **ctx: Any) -> None:
        self.messages.append(DiagMessage(DiagLevel.WARNING, source, message, ctx))

    def error(self, source: str, message: str, **ctx: Any) -> None:
        self.messages.append(DiagMessage(DiagLevel.ERROR, source, message, ctx))

    @property
    def has_errors(self) -> bool:
        return any(m.level == DiagLevel.ERROR for m in self.messages)

    @property
    def has_warnings(self) -> bool:
        return any(m.level == DiagLevel.WARNING for m in self.messages)

    def merge(self, other: Diagnostics) -> None:
        self.messages.extend(other.messages)


# ── Core Data Contracts ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class UniverseSnapshot:
    """DataFrame of OHLCV + fundamentals for all stocks on a rebalance date, PiT-enforced.

    data: DataFrame indexed by symbol, columns include OHLCV + fundamental fields.
    rebalance_date: The date this snapshot represents.
    universe_size: Number of stocks in the universe after filters.
    """

    data: pd.DataFrame
    rebalance_date: date
    universe_size: int


@dataclass(frozen=True)
class FeatureMatrix:
    """DataFrame indexed by (date, symbol), one column per factor, rank-percentile [0,1].

    data: MultiIndex DataFrame. ALL values in [0, 1] after normalization.
    factor_names: List of factor column names present.
    rebalance_date: Date this matrix was computed for.
    """

    data: pd.DataFrame
    factor_names: list[str]
    rebalance_date: date


@dataclass(frozen=True)
class GateVerdict:
    """Result of evaluating a factor through G0-G5 gates."""

    factor_name: str
    gate_results: dict[str, bool]  # {"G0": True, "G1": False, ...}
    gate_metrics: dict[str, float]  # {"G0_value": 0.85, "G1_value": 0.015, ...}
    passed_all: bool


@dataclass(frozen=True)
class CompositeScore:
    """Per-stock combined score for a single rebalance date."""

    scores: pd.Series  # Index: symbol, Values: combined score
    rebalance_date: date
    model_type: str  # "ridge", "gbm", "neural"
    feature_importance: dict[str, float]


@dataclass(frozen=True)
class TradePlan:
    """THE critical interface between research pipeline and execution engine.

    One TradePlan per stock per rebalance event.
    """

    symbol: str
    side: Side
    target_shares: int
    current_shares: int
    order_type: str  # "TWAP", "VWAP", "MARKET"
    reason: str  # Human-readable: "new_entry", "rebalance", "exit_signal", "exit_risk"
    decision_timestamp: datetime
    execution_timestamp: datetime | None = None
    estimated_cost_bps: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PortfolioBuildResult:
    """Complete output of a rebalance cycle."""

    trade_plans: list[TradePlan]
    cost_estimate_usd: float
    turnover_pct: float
    regime_state: RegimeState
    rebalance_date: date
    held_positions: int
    new_entries: int
    exits: int
    skipped_reason: str | None = None  # Non-None if rebalance was skipped


@dataclass(frozen=True)
class BacktestResult:
    """Output of a rigorous walk-forward backtest."""

    daily_returns: pd.Series
    oos_sharpe: float
    oos_cagr: float
    max_drawdown: float
    annual_turnover: float
    cost_drag_pct: float
    per_fold_sharpe: list[float]
    per_factor_contribution: dict[str, float]
    permutation_p_value: float | None = None
    bootstrap_ci_lower: float | None = None
    bootstrap_ci_upper: float | None = None
    romano_wolf_p_values: dict[str, float] | None = None
    # Benchmark metrics keyed by ticker (e.g. "SPY", "RSP"); each value is a
    # dict with keys {"sharpe", "cagr", "max_drawdown"} computed over the same
    # OOS date range as ``daily_returns``. Populated by
    # ``run_walk_forward_backtest`` when ``benchmark_returns`` is supplied.
    # Per RALPH TODO-9: RSP is the equal-weight peer reported ALONGSIDE SPY;
    # neither benchmark changes the regime overlay which stays on SPY.
    benchmark_metrics: dict[str, dict[str, float]] | None = None


@dataclass(frozen=True)
class FalsificationCheckResult:
    """Result of checking one falsification trigger."""

    trigger_id: str  # "F1", "F2", ...
    trigger_name: str
    current_value: float
    threshold: float
    severity: Severity
    passed: bool  # True = no trigger fired (healthy)
    description: str


@dataclass(frozen=True)
class ThresholdCheck:
    """Generic threshold evaluation result (shared by gates and falsification)."""

    name: str
    metric_name: str
    current_value: float
    threshold: float
    direction: str  # ">=", ">", "<", "<="
    passed: bool


@dataclass(frozen=True)
class AttributionReport:
    """Per-factor and per-sector return contribution for a period."""

    factor_contributions: dict[str, float]
    sector_contributions: dict[str, float]
    total_return: float
    period_start: date
    period_end: date


@dataclass(frozen=True)
class DriftCheckResult:
    """Model drift detection output."""

    factor_name: str
    rolling_ic: float
    drift_detected: bool
    retrain_recommended: bool
    ic_threshold: float
