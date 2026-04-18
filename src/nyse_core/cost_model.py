"""Dynamic transaction cost calculator.

Models roundtrip trading cost as a function of ADV, day-of-week effects,
and earnings proximity.  Implements Carver's position inertia to suppress
noise-driven rebalancing.
"""

from __future__ import annotations

import math

from nyse_core.contracts import Diagnostics
from nyse_core.schema import (
    BASE_SPREAD_BPS,
    DEFAULT_COMMISSION_PER_SHARE,
    EARNINGS_WEEK_MULTIPLIER,
    MONDAY_MULTIPLIER,
    POSITION_INERTIA_THRESHOLD,
)

_SRC = "cost_model"

# Assumed average share price for commission-to-bps conversion
_ESTIMATED_PRICE: float = 50.0


def estimate_cost_bps(
    adv: float,
    is_monday: bool = False,
    is_earnings_week: bool = False,
) -> tuple[float, Diagnostics]:
    """Estimate roundtrip transaction cost in basis points.

    Parameters
    ----------
    adv : float
        Average daily dollar volume (20-day).
    is_monday : bool
        Whether the trade day is Monday (wider spreads).
    is_earnings_week : bool
        Whether the stock reports earnings this week.

    Returns
    -------
    tuple[float, Diagnostics]
        (total_cost_bps, diagnostics)
    """
    diag = Diagnostics()

    if adv <= 0:
        diag.error(_SRC, "adv must be positive", adv=adv)
        return 10_000.0, diag

    # Dynamic spread: penalise illiquid names
    spread_bps = BASE_SPREAD_BPS / math.sqrt(adv / 50_000_000)

    if is_monday:
        spread_bps *= MONDAY_MULTIPLIER
    if is_earnings_week:
        spread_bps *= EARNINGS_WEEK_MULTIPLIER

    # Commission component (both sides)
    commission_bps = DEFAULT_COMMISSION_PER_SHARE * 2 / _ESTIMATED_PRICE * 10_000

    total = spread_bps + commission_bps

    diag.info(
        _SRC,
        "cost estimated",
        spread_bps=round(spread_bps, 4),
        commission_bps=round(commission_bps, 4),
        total_bps=round(total, 4),
        is_monday=is_monday,
        is_earnings_week=is_earnings_week,
    )
    return total, diag


def should_trade(
    current_weight: float,
    target_weight: float,
    cost_bps: float,
    inertia_threshold: float = POSITION_INERTIA_THRESHOLD,
) -> tuple[bool, Diagnostics]:
    """Decide whether a weight change justifies a trade (Carver position inertia).

    Parameters
    ----------
    current_weight : float
        Current portfolio weight (e.g. 0.05 = 5%).
    target_weight : float
        Target portfolio weight after rebalance.
    cost_bps : float
        Estimated roundtrip cost in basis points.
    inertia_threshold : float
        Minimum absolute weight delta to justify trading.

    Returns
    -------
    tuple[bool, Diagnostics]
        (trade: bool, diagnostics)
    """
    diag = Diagnostics()
    delta = abs(target_weight - current_weight)
    trade = delta > inertia_threshold

    if trade:
        diag.info(
            _SRC,
            "trade approved: delta exceeds inertia threshold",
            delta=round(delta, 6),
            threshold=inertia_threshold,
            cost_bps=round(cost_bps, 4),
        )
    else:
        diag.info(
            _SRC,
            "trade suppressed: delta within inertia threshold",
            delta=round(delta, 6),
            threshold=inertia_threshold,
            cost_bps=round(cost_bps, 4),
        )

    return trade, diag
