"""Execution bridge between TradePlan and NautilusTrader.

Handles three modes:
  - PAPER: simulate fills at market price + estimated slippage
  - SHADOW: track real prices but don't submit orders (logging only)
  - LIVE: submit to NautilusTrader (future implementation)

All public methods return (result, Diagnostics) tuples to stay
consistent with the nyse_core convention.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from nyse_core.contracts import Diagnostics, TradePlan
from nyse_core.corporate_actions import detect_pending_actions
from nyse_core.schema import Side

if TYPE_CHECKING:
    import pandas as pd

    from nyse_ats.storage.live_store import LiveStore

_SRC = "nautilus_bridge"

# ── Execution mode constants ────────────────────────────────────────────────

MODE_PAPER = "paper"
MODE_SHADOW = "shadow"
MODE_LIVE = "live"
_VALID_MODES = {MODE_PAPER, MODE_SHADOW, MODE_LIVE}

# ── Paper simulation defaults ───────────────────────────────────────────────

_DEFAULT_SLIPPAGE_MEAN_BPS = 2.5
_DEFAULT_SLIPPAGE_STD_BPS = 1.5
_MAX_SLIPPAGE_BPS = 5.0
_REJECTION_PROBABILITY = 0.02  # 2% random rejection


# ── Data contracts ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FillResult:
    """Outcome of a single order execution attempt."""

    symbol: str
    side: str
    requested_shares: int
    filled_shares: int
    fill_price: float
    slippage_bps: float
    fill_timestamp: datetime
    rejected: bool = False
    rejection_reason: str = ""
    is_shadow: bool = False


# ── Bridge ──────────────────────────────────────────────────────────────────


class NautilusBridge:
    """Bridge between TradePlan objects and the execution venue.

    Parameters
    ----------
    mode : str
        One of ``"paper"``, ``"shadow"``, ``"live"``.
    live_store : LiveStore | None
        Required for ``reconcile()``; optional otherwise.
    kill_switch : bool
        When True, ``submit()`` rejects ALL orders.
    rng_seed : int | None
        Seed for the random-number generator used in paper fills.
        Pass an integer for deterministic test behaviour.
    """

    def __init__(
        self,
        mode: str = MODE_PAPER,
        live_store: LiveStore | None = None,
        kill_switch: bool = False,
        rng_seed: int | None = None,
    ) -> None:
        if mode not in _VALID_MODES:
            raise ValueError(f"Invalid mode '{mode}'. Must be one of {_VALID_MODES}")
        self._mode = mode
        self._live_store = live_store
        self._kill_switch = kill_switch
        self._rng = random.Random(rng_seed)

    # ── Pre-submit ──────────────────────────────────────────────────────────

    def pre_submit(
        self,
        plans: list[TradePlan],
        corporate_actions: pd.DataFrame | None = None,
    ) -> tuple[list[TradePlan], Diagnostics]:
        """Screen plans for corporate actions since signal generation.

        If a corporate action is detected for a symbol in *plans*, that
        plan is removed from the returned list and a WARNING is logged.

        Parameters
        ----------
        plans : list[TradePlan]
            Candidate trade plans from the portfolio builder.
        corporate_actions : pd.DataFrame | None
            Corporate action calendar. Columns: ``date``, ``symbol``,
            ``action_type``.  ``None`` means "no calendar available".

        Returns
        -------
        tuple[list[TradePlan], Diagnostics]
        """
        diag = Diagnostics()

        if not plans:
            diag.info(_SRC, "pre_submit: empty plan list — no-op")
            return [], diag

        if corporate_actions is None or corporate_actions.empty:
            diag.info(_SRC, "pre_submit: no corporate actions to check")
            return list(plans), diag

        # Build the held-symbols list from plan symbols
        held_symbols = [tp.symbol for tp in plans]

        # Use the earliest decision_timestamp as the look-back boundary
        earliest = min(tp.decision_timestamp for tp in plans)
        since_date = earliest.date()

        pending, ca_diag = detect_pending_actions(
            held_symbols=held_symbols,
            actions=corporate_actions,
            since=since_date,
        )
        diag.merge(ca_diag)

        if not pending:
            return list(plans), diag

        affected_symbols = {a["symbol"] for a in pending}
        filtered = [tp for tp in plans if tp.symbol not in affected_symbols]

        diag.warning(
            _SRC,
            f"pre_submit: cancelled {len(plans) - len(filtered)} plan(s) due to corporate actions",
            affected_symbols=sorted(affected_symbols),
        )
        return filtered, diag

    # ── Submit ──────────────────────────────────────────────────────────────

    def submit(
        self,
        plans: list[TradePlan],
        market_prices: dict[str, float],
    ) -> tuple[list[FillResult], Diagnostics]:
        """Execute trade plans according to the current mode.

        Parameters
        ----------
        plans : list[TradePlan]
            Trade plans to execute.
        market_prices : dict[str, float]
            Current market price per symbol, used for paper/shadow fills.

        Returns
        -------
        tuple[list[FillResult], Diagnostics]
        """
        diag = Diagnostics()

        if not plans:
            diag.info(_SRC, "submit: empty plan list — no-op")
            return [], diag

        # ── Kill switch ─────────────────────────────────────────────────────
        if self._kill_switch:
            now = datetime.now(UTC)
            fills = [
                FillResult(
                    symbol=tp.symbol,
                    side=tp.side.value,
                    requested_shares=tp.target_shares,
                    filled_shares=0,
                    fill_price=0.0,
                    slippage_bps=0.0,
                    fill_timestamp=now,
                    rejected=True,
                    rejection_reason="kill_switch_active",
                )
                for tp in plans
            ]
            diag.warning(
                _SRC,
                f"kill switch active — rejected all {len(plans)} order(s)",
            )
            return fills, diag

        # ── Mode dispatch ───────────────────────────────────────────────────
        if self._mode == MODE_LIVE:
            raise NotImplementedError("Live execution requires NautilusTrader")

        if self._mode == MODE_SHADOW:
            return self._shadow_submit(plans, market_prices, diag)

        # MODE_PAPER
        return self._paper_submit(plans, market_prices, diag)

    # ── Reconcile ───────────────────────────────────────────────────────────

    def reconcile(self, fills: list[FillResult]) -> Diagnostics:
        """Write fill state to *live_store* — the position source of truth.

        Skips rejected fills.  Raises ``RuntimeError`` if no live_store
        was provided at construction time.
        """
        diag = Diagnostics()

        if self._live_store is None:
            diag.error(_SRC, "reconcile called but no LiveStore configured")
            return diag

        successful = [f for f in fills if not f.rejected and not f.is_shadow]
        if not successful:
            diag.info(_SRC, "reconcile: no successful fills to record")
            return diag

        try:
            for f in successful:
                side_str = f.side if isinstance(f.side, str) else f.side.value
                fill_diag = self._live_store.record_fill(
                    symbol=f.symbol,
                    side=side_str,
                    filled_shares=f.filled_shares,
                    fill_price=f.fill_price,
                    fill_timestamp=f.fill_timestamp,
                    slippage_bps=f.slippage_bps,
                )
                diag.merge(fill_diag)
            diag.info(
                _SRC,
                f"reconciled {len(successful)} fill(s) to LiveStore",
            )
        except Exception as exc:  # noqa: BLE001
            diag.error(
                _SRC,
                f"reconcile failed: {exc}",
                error_type=type(exc).__name__,
            )

        return diag

    # ── Private: paper simulation ───────────────────────────────────────────

    def _paper_submit(
        self,
        plans: list[TradePlan],
        market_prices: dict[str, float],
        diag: Diagnostics,
    ) -> tuple[list[FillResult], Diagnostics]:
        """Simulate fills with random slippage and a small rejection rate."""
        now = datetime.now(UTC)
        fills: list[FillResult] = []

        for tp in plans:
            price = market_prices.get(tp.symbol)
            if price is None:
                fills.append(
                    FillResult(
                        symbol=tp.symbol,
                        side=tp.side.value,
                        requested_shares=tp.target_shares,
                        filled_shares=0,
                        fill_price=0.0,
                        slippage_bps=0.0,
                        fill_timestamp=now,
                        rejected=True,
                        rejection_reason="no_market_price",
                    )
                )
                diag.warning(
                    _SRC,
                    f"no market price for {tp.symbol} — order rejected",
                )
                continue

            # Random rejection (2%)
            if self._rng.random() < _REJECTION_PROBABILITY:
                fills.append(
                    FillResult(
                        symbol=tp.symbol,
                        side=tp.side.value,
                        requested_shares=tp.target_shares,
                        filled_shares=0,
                        fill_price=0.0,
                        slippage_bps=0.0,
                        fill_timestamp=now,
                        rejected=True,
                        rejection_reason="random_rejection",
                    )
                )
                diag.info(
                    _SRC,
                    f"simulated random rejection for {tp.symbol}",
                )
                continue

            # Slippage: normal(mean, std) clipped to [0, max]
            raw_slip = self._rng.gauss(_DEFAULT_SLIPPAGE_MEAN_BPS, _DEFAULT_SLIPPAGE_STD_BPS)
            slippage_bps = max(0.0, min(raw_slip, _MAX_SLIPPAGE_BPS))

            slip_mult = 1.0 + (slippage_bps / 10_000)
            fill_price = price * slip_mult if tp.side == Side.BUY else price / slip_mult

            fills.append(
                FillResult(
                    symbol=tp.symbol,
                    side=tp.side.value,
                    requested_shares=tp.target_shares,
                    filled_shares=tp.target_shares,
                    fill_price=round(fill_price, 4),
                    slippage_bps=round(slippage_bps, 2),
                    fill_timestamp=now,
                )
            )

        n_ok = sum(1 for f in fills if not f.rejected)
        diag.info(
            _SRC,
            f"paper submit: {n_ok}/{len(fills)} fills successful",
        )
        return fills, diag

    # ── Private: shadow mode ────────────────────────────────────────────────

    def _shadow_submit(
        self,
        plans: list[TradePlan],
        market_prices: dict[str, float],
        diag: Diagnostics,
    ) -> tuple[list[FillResult], Diagnostics]:
        """Log hypothetical fills at market price without executing."""
        now = datetime.now(UTC)
        fills: list[FillResult] = []

        for tp in plans:
            price = market_prices.get(tp.symbol, 0.0)
            fills.append(
                FillResult(
                    symbol=tp.symbol,
                    side=tp.side.value,
                    requested_shares=tp.target_shares,
                    filled_shares=0,  # Shadow never fills
                    fill_price=price,
                    slippage_bps=0.0,
                    fill_timestamp=now,
                    is_shadow=True,
                )
            )

        diag.info(
            _SRC,
            f"shadow submit: tracked {len(fills)} plan(s) at market price",
        )
        return fills, diag
