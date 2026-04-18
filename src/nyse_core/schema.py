"""Canonical column names, constants, and TypedDicts for the NYSE ATS framework.

All modules import column names from here — no magic strings elsewhere.
"""

from __future__ import annotations

from enum import StrEnum, unique
from typing import Final

# ── Trading Calendar ──────────────────────────────────────────────────────────
TRADING_DAYS_PER_YEAR: Final[int] = 252
STRICT_CALENDAR: Final[bool] = True  # AP-5: never forward-fill prices by default

# ── Canonical Column Names (OHLCV) ────────────────────────────────────────────
COL_DATE: Final[str] = "date"
COL_SYMBOL: Final[str] = "symbol"
COL_OPEN: Final[str] = "open"
COL_HIGH: Final[str] = "high"
COL_LOW: Final[str] = "low"
COL_CLOSE: Final[str] = "close"
COL_VOLUME: Final[str] = "volume"
COL_ADJ_CLOSE: Final[str] = "adj_close"

OHLCV_COLUMNS: Final[list[str]] = [
    COL_DATE,
    COL_SYMBOL,
    COL_OPEN,
    COL_HIGH,
    COL_LOW,
    COL_CLOSE,
    COL_VOLUME,
]

# ── Canonical Column Names (Features) ─────────────────────────────────────────
COL_FACTOR: Final[str] = "factor_name"
COL_SCORE: Final[str] = "composite_score"
COL_RANK_PCT: Final[str] = "rank_pct"
COL_FORWARD_RET_5D: Final[str] = "fwd_ret_5d"
COL_FORWARD_RET_20D: Final[str] = "fwd_ret_20d"
COL_SECTOR: Final[str] = "gics_sector"
COL_MARKET_CAP: Final[str] = "market_cap"
COL_ADV_20D: Final[str] = "adv_20d"

# ── Canonical Column Names (Portfolio) ────────────────────────────────────────
COL_WEIGHT: Final[str] = "weight"
COL_TARGET_SHARES: Final[str] = "target_shares"
COL_SIDE: Final[str] = "side"
COL_REASON: Final[str] = "reason"


@unique
class Side(StrEnum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@unique
class Severity(StrEnum):
    """Alert severity for falsification triggers."""

    VETO = "VETO"
    WARNING = "WARNING"


@unique
class UsageDomain(StrEnum):
    """Factor usage domain — prevents double-dip (AP-3)."""

    SIGNAL = "SIGNAL"
    RISK = "RISK"


@unique
class RegimeState(StrEnum):
    """Market regime from SMA200 binary overlay."""

    BULL = "BULL"
    BEAR = "BEAR"


@unique
class RebalanceFrequency(StrEnum):
    """Rebalance cadence."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"


@unique
class CombinationModelType(StrEnum):
    """Model type for signal combination."""

    RIDGE = "ridge"
    GBM = "gbm"
    NEURAL = "neural"


@unique
class NormalizationMethod(StrEnum):
    """Normalization method for features."""

    RANK_PERCENTILE = "rank_percentile"
    WINSORIZE = "winsorize"
    Z_SCORE = "z_score"


# ── Universe Filters ──────────────────────────────────────────────────────────
DEFAULT_MIN_PRICE: Final[float] = 5.0
DEFAULT_MIN_ADV_20D: Final[int] = 500_000
DEFAULT_TOP_N: Final[int] = 20

# ── Risk Limits ───────────────────────────────────────────────────────────────
MAX_POSITION_PCT: Final[float] = 0.10
MAX_SECTOR_PCT: Final[float] = 0.30
POSITION_INERTIA_THRESHOLD: Final[float] = 0.005  # Carver 10% relative → 0.5pp for 5% target
DEFAULT_SELL_BUFFER: Final[float] = 1.5
BETA_CAP_LOW: Final[float] = 0.5
BETA_CAP_HIGH: Final[float] = 1.5
DAILY_LOSS_LIMIT: Final[float] = -0.03
EARNINGS_EVENT_CAP: Final[float] = 0.05
EARNINGS_EVENT_DAYS: Final[int] = 2

# ── Regime Overlay ────────────────────────────────────────────────────────────
BULL_EXPOSURE: Final[float] = 1.0
BEAR_EXPOSURE: Final[float] = 0.4
SMA_WINDOW: Final[int] = 200

# ── CV Parameters ─────────────────────────────────────────────────────────────
MIN_TRAIN_YEARS: Final[int] = 2
DEFAULT_PURGE_DAYS: Final[int] = 5
DEFAULT_EMBARGO_DAYS: Final[int] = 5
DEFAULT_TEST_MONTHS: Final[int] = 6
MAX_PARAMS_WARNING: Final[int] = 5  # AP-7

# ── Cost Model ────────────────────────────────────────────────────────────────
DEFAULT_COMMISSION_PER_SHARE: Final[float] = 0.005
BASE_SPREAD_BPS: Final[float] = 10.0
MONDAY_MULTIPLIER: Final[float] = 1.3
EARNINGS_WEEK_MULTIPLIER: Final[float] = 1.5
