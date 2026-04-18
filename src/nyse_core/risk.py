"""10-layer risk management functions.

Layers implemented in this module:
  1. Regime overlay (SMA200)
  2. Position caps
  3. Sector caps
  4. Beta cap check
  5. Daily loss halt check
  6. Earnings exposure cap
"""

from __future__ import annotations

from nyse_core.contracts import Diagnostics
from nyse_core.schema import (
    BEAR_EXPOSURE,
    BETA_CAP_HIGH,
    BETA_CAP_LOW,
    BULL_EXPOSURE,
    DAILY_LOSS_LIMIT,
    EARNINGS_EVENT_CAP,
    EARNINGS_EVENT_DAYS,
    MAX_POSITION_PCT,
    MAX_SECTOR_PCT,
    RegimeState,
)

_SRC = "risk"


# ── Layer 1: Regime overlay ──────────────────────────────────────────────────


def apply_regime_overlay(
    exposure: float,
    spy_price: float,
    spy_sma200: float,
) -> tuple[float, RegimeState, Diagnostics]:
    """Scale exposure by market regime (SPY vs SMA200).

    Parameters
    ----------
    exposure : float
        Pre-overlay gross exposure (typically 1.0).
    spy_price : float
        Current SPY price.
    spy_sma200 : float
        SPY 200-day simple moving average.

    Returns
    -------
    tuple[float, RegimeState, Diagnostics]
    """
    diag = Diagnostics()

    if spy_price > spy_sma200:
        regime = RegimeState.BULL
        scaled = exposure * BULL_EXPOSURE
    else:
        regime = RegimeState.BEAR
        scaled = exposure * BEAR_EXPOSURE

    diag.info(
        _SRC,
        f"regime overlay applied: {regime.value}",
        spy_price=spy_price,
        spy_sma200=spy_sma200,
        original_exposure=exposure,
        scaled_exposure=round(scaled, 6),
    )
    return scaled, regime, diag


# ── Layer 2: Position caps ───────────────────────────────────────────────────


def apply_position_caps(
    weights: dict[str, float],
    max_pct: float = MAX_POSITION_PCT,
) -> tuple[dict[str, float], Diagnostics]:
    """Cap individual positions and redistribute excess pro-rata.

    Parameters
    ----------
    weights : dict[str, float]
        {symbol: weight} — weights should sum to ~1.0.
    max_pct : float
        Maximum allowed weight for any single position.

    Returns
    -------
    tuple[dict[str, float], Diagnostics]
    """
    diag = Diagnostics()

    if not weights:
        return {}, diag

    capped = dict(weights)
    sum(weights.values())
    capped_syms_set: set[str] = set()

    for _iteration in range(50):
        over = {s: w for s, w in capped.items() if w > max_pct + 1e-12}
        if not over:
            break

        for sym in over:
            capped_syms_set.add(sym)

        excess = sum(w - max_pct for w in over.values())
        for sym in over:
            capped[sym] = max_pct

        # Redistribute to positions still below the cap
        under = {s: w for s, w in capped.items() if s not in capped_syms_set}
        total_under = sum(under.values())
        if total_under <= 0:
            break

        for sym in under:
            capped[sym] += excess * (under[sym] / total_under)

        diag.debug(_SRC, "position cap iteration", excess=round(excess, 6))

    if capped_syms_set:
        diag.info(
            _SRC,
            "positions capped",
            capped_symbols=sorted(capped_syms_set),
            max_pct=max_pct,
        )

    return capped, diag


# ── Layer 3: Sector caps ────────────────────────────────────────────────────


def apply_sector_caps(
    weights: dict[str, float],
    sectors: dict[str, str],
    max_sector_pct: float = MAX_SECTOR_PCT,
) -> tuple[dict[str, float], Diagnostics]:
    """Cap sector exposure and redistribute excess pro-rata.

    Parameters
    ----------
    weights : dict[str, float]
        {symbol: weight}.
    sectors : dict[str, str]
        {symbol: GICS_sector}.
    max_sector_pct : float
        Maximum allowed total weight for any single sector.

    Returns
    -------
    tuple[dict[str, float], Diagnostics]
    """
    diag = Diagnostics()

    if not weights:
        return {}, diag

    capped = dict(weights)
    capped_sector_names: list[str] = []
    frozen_sectors: set[str] = set()

    for _ in range(50):
        sector_totals: dict[str, float] = {}
        for sym, w in capped.items():
            sec = sectors.get(sym, "Unknown")
            sector_totals[sec] = sector_totals.get(sec, 0.0) + w

        over_sectors = {
            s: t for s, t in sector_totals.items() if t > max_sector_pct + 1e-12 and s not in frozen_sectors
        }
        if not over_sectors:
            break

        capped_sector_names = list(over_sectors.keys())

        for sec, total in over_sectors.items():
            excess = total - max_sector_pct
            frozen_sectors.add(sec)

            sec_syms = [s for s in capped if sectors.get(s, "Unknown") == sec]
            for sym in sec_syms:
                reduction = excess * (capped[sym] / total)
                capped[sym] -= reduction

            other_syms = [s for s in capped if sectors.get(s, "Unknown") not in frozen_sectors]
            total_other = sum(capped[s] for s in other_syms)
            if total_other > 0:
                for sym in other_syms:
                    capped[sym] += excess * (capped[sym] / total_other)

        diag.debug(_SRC, "sector cap iteration", over_sectors=capped_sector_names)

    if capped_sector_names:
        diag.info(
            _SRC,
            "sectors capped",
            sectors=capped_sector_names,
            max_sector_pct=max_sector_pct,
        )

    return capped, diag


# ── Layer 4: Beta cap check ──────────────────────────────────────────────────


def check_beta_cap(
    portfolio_beta: float,
    low: float = BETA_CAP_LOW,
    high: float = BETA_CAP_HIGH,
) -> tuple[bool, Diagnostics]:
    """Check if portfolio beta is within acceptable range.

    Returns
    -------
    tuple[bool, Diagnostics]
        (within_range: bool, diagnostics)
    """
    diag = Diagnostics()
    within = low <= portfolio_beta <= high

    if within:
        diag.info(_SRC, "beta within range", beta=portfolio_beta, low=low, high=high)
    else:
        diag.warning(_SRC, "beta out of range", beta=portfolio_beta, low=low, high=high)

    return within, diag


# ── Layer 5: Daily loss halt ─────────────────────────────────────────────────


def check_daily_loss(
    daily_return: float,
    limit: float = DAILY_LOSS_LIMIT,
) -> tuple[bool, Diagnostics]:
    """Check if daily loss triggers a halt.

    Returns
    -------
    tuple[bool, Diagnostics]
        (halt_trading: bool, diagnostics)
    """
    diag = Diagnostics()
    halt = daily_return <= limit

    if halt:
        diag.warning(
            _SRC,
            "daily loss limit breached — halt trading",
            daily_return=daily_return,
            limit=limit,
        )
    else:
        diag.info(_SRC, "daily loss within limit", daily_return=daily_return, limit=limit)

    return halt, diag


# ── Layer 6: Earnings exposure cap ───────────────────────────────────────────


def check_earnings_exposure(
    weights: dict[str, float],
    reporting_within_days: dict[str, int],
    cap: float = EARNINGS_EVENT_CAP,
    days: int = EARNINGS_EVENT_DAYS,
) -> tuple[dict[str, float], Diagnostics]:
    """Cap weight for stocks reporting earnings within ``days`` trading days.

    Parameters
    ----------
    weights : dict[str, float]
        {symbol: weight}.
    reporting_within_days : dict[str, int]
        {symbol: days_until_earnings}. Only stocks with upcoming earnings
        need be included.
    cap : float
        Maximum weight for a stock near earnings.
    days : int
        Threshold: stocks reporting within this many days are capped.

    Returns
    -------
    tuple[dict[str, float], Diagnostics]
    """
    diag = Diagnostics()

    if not weights:
        return {}, diag

    result = dict(weights)
    total_excess = 0.0

    near_earnings = [
        sym for sym, d in reporting_within_days.items() if d <= days and sym in result and result[sym] > cap
    ]

    for sym in near_earnings:
        excess = result[sym] - cap
        total_excess += excess
        result[sym] = cap
        diag.info(
            _SRC,
            f"capped {sym} due to earnings proximity",
            days_to_earnings=reporting_within_days[sym],
            original_weight=round(weights[sym], 6),
            capped_weight=cap,
        )

    # Redistribute excess pro-rata to non-earnings stocks
    if total_excess > 0:
        safe_syms = [s for s in result if s not in near_earnings]
        total_safe = sum(result[s] for s in safe_syms)
        if total_safe > 0:
            for sym in safe_syms:
                result[sym] += total_excess * (result[sym] / total_safe)

    return result, diag
