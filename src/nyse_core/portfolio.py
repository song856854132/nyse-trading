"""Portfolio builder — orchestrates allocation, risk, and cost modules.

Entry point: ``build_portfolio`` runs the full rebalance pipeline:
  select_top_n -> equal_weight -> regime_overlay -> position_caps -> sector_caps
Then generates TradePlan objects and computes turnover/cost estimates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from nyse_core.allocator import equal_weight, select_top_n
from nyse_core.contracts import Diagnostics, PortfolioBuildResult, TradePlan
from nyse_core.cost_model import estimate_cost_bps
from nyse_core.risk import (
    apply_position_caps,
    apply_regime_overlay,
    apply_sector_caps,
    check_beta_cap,
    check_earnings_exposure,
)
from nyse_core.schema import (
    DEFAULT_SELL_BUFFER,
    DEFAULT_TOP_N,
    MAX_POSITION_PCT,
    MAX_SECTOR_PCT,
    POSITION_INERTIA_THRESHOLD,
    Side,
)

if TYPE_CHECKING:
    import pandas as pd

_SRC = "portfolio"


def build_portfolio(
    scores: pd.Series,
    current_holdings: dict[str, float],
    sectors: dict[str, str],
    spy_price: float,
    spy_sma200: float,
    config: dict,
) -> tuple[PortfolioBuildResult, Diagnostics]:
    """Build a complete portfolio from composite scores.

    Parameters
    ----------
    scores : pd.Series
        Index = symbol, values = composite score (higher = better).
    current_holdings : dict[str, float]
        {symbol: current_weight} for positions held.
    sectors : dict[str, str]
        {symbol: GICS_sector} for all scored stocks.
    spy_price : float
        Current SPY price.
    spy_sma200 : float
        SPY 200-day SMA.
    config : dict
        Override keys: ``top_n``, ``sell_buffer``, ``max_position_pct``,
        ``max_sector_pct``, ``inertia_threshold``, ``rebalance_date``.

    Returns
    -------
    tuple[PortfolioBuildResult, Diagnostics]
    """
    diag = Diagnostics()
    now = datetime.now(UTC)

    top_n = config.get("top_n", DEFAULT_TOP_N)
    sell_buffer = config.get("sell_buffer", DEFAULT_SELL_BUFFER)
    max_pos = config.get("max_position_pct", MAX_POSITION_PCT)
    max_sec = config.get("max_sector_pct", MAX_SECTOR_PCT)
    inertia = config.get("inertia_threshold", POSITION_INERTIA_THRESHOLD)
    rebalance_date = config.get("rebalance_date")
    if rebalance_date is None:
        raise ValueError("config['rebalance_date'] is required")
    base_provenance: dict = config.get("provenance", {})

    # Step 1: Select top-N with sell buffer
    held_set = set(current_holdings.keys())
    selected, d1 = select_top_n(scores, n=top_n, current_holdings=held_set, sell_buffer=sell_buffer)
    diag.merge(d1)

    # Step 2: Equal weight
    weights, d2 = equal_weight(selected)
    diag.merge(d2)

    # Step 3: Regime overlay — scale all weights
    total_exposure = sum(weights.values())
    scaled_exposure, regime, d3 = apply_regime_overlay(total_exposure, spy_price, spy_sma200)
    diag.merge(d3)

    if total_exposure > 0:
        scale_factor = scaled_exposure / total_exposure
        weights = {s: w * scale_factor for s, w in weights.items()}

    # Step 4: Position caps
    weights, d4 = apply_position_caps(weights, max_pct=max_pos)
    diag.merge(d4)

    # Step 5: Sector caps
    weights, d5 = apply_sector_caps(weights, sectors, max_sector_pct=max_sec)
    diag.merge(d5)

    # Step 6: Earnings exposure cap (when earnings calendar is available)
    reporting_within_days: dict[str, int] = config.get("reporting_within_days", {})
    if reporting_within_days:
        earnings_cap = config.get("earnings_event_cap", 0.05)
        earnings_days = config.get("earnings_event_days", 2)
        weights, d6 = check_earnings_exposure(
            weights,
            reporting_within_days,
            cap=earnings_cap,
            days=earnings_days,
        )
        diag.merge(d6)

    # Step 7: Beta cap check (when portfolio beta is available)
    portfolio_beta: float | None = config.get("portfolio_beta")
    if portfolio_beta is not None:
        beta_low = config.get("beta_cap_low", 0.5)
        beta_high = config.get("beta_cap_high", 1.5)
        within_range, d7 = check_beta_cap(portfolio_beta, low=beta_low, high=beta_high)
        diag.merge(d7)
        if not within_range:
            diag.warning(
                _SRC,
                f"portfolio beta {portfolio_beta:.2f} outside [{beta_low}, {beta_high}]",
            )

    # Build TradePlans
    all_symbols = set(weights.keys()) | held_set
    trade_plans: list[TradePlan] = []
    new_entries = 0
    exits = 0
    turnover = 0.0

    for sym in sorted(all_symbols):
        target_w = weights.get(sym, 0.0)
        current_w = current_holdings.get(sym, 0.0)
        delta = target_w - current_w

        # Check inertia
        if abs(delta) <= inertia and target_w > 0 and current_w > 0:
            continue

        if delta > 0:
            side = Side.BUY
            reason = "new_entry" if current_w == 0.0 else "rebalance"
            if current_w == 0.0:
                new_entries += 1
        elif delta < 0:
            side = Side.SELL
            if target_w == 0.0:
                reason = "exit_signal"
                exits += 1
            else:
                reason = "rebalance"
        else:
            continue

        # Estimate cost
        adv = config.get("adv", {}).get(sym, 50_000_000)
        cost, dc = estimate_cost_bps(adv)
        diag.merge(dc)

        turnover += abs(delta)

        # Convert weights to shares using notional value and per-stock price
        notional = config.get("notional", 1_000_000)
        prices = config.get("prices", {})
        price = prices.get(sym, 50.0)  # Default price for paper trading
        t_shares = int(abs(target_w) * notional / price) if price > 0 else 0
        c_shares = int(abs(current_w) * notional / price) if price > 0 else 0

        # Per-trade provenance: base pipeline context + trade-specific fields
        tp_provenance = {
            **base_provenance,
            "composite_score": round(float(scores.get(sym, 0.0)), 6),
            "target_weight": round(target_w, 6),
        }

        trade_plans.append(
            TradePlan(
                symbol=sym,
                side=side,
                target_shares=t_shares,
                current_shares=c_shares,
                order_type="TWAP",
                reason=reason,
                decision_timestamp=now,
                estimated_cost_bps=cost,
                provenance=tp_provenance,
            )
        )

    # Cost estimate in USD (approximate: turnover * cost * notional)
    avg_cost_bps = sum(tp.estimated_cost_bps for tp in trade_plans) / len(trade_plans) if trade_plans else 0.0
    notional = config.get("notional", 1_000_000)
    cost_estimate_usd = turnover * (avg_cost_bps / 10_000) * notional

    result = PortfolioBuildResult(
        trade_plans=trade_plans,
        cost_estimate_usd=round(cost_estimate_usd, 2),
        turnover_pct=round(turnover, 6),
        regime_state=regime,
        rebalance_date=rebalance_date,
        held_positions=len([s for s in weights if weights[s] > 0]),
        new_entries=new_entries,
        exits=exits,
    )

    diag.info(
        _SRC,
        "portfolio built",
        trades=len(trade_plans),
        turnover=round(turnover, 4),
        regime=regime.value,
        new_entries=new_entries,
        exits=exits,
    )

    return result, diag
