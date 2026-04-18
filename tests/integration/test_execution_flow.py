"""Integration tests: execution flow from TradePlan to fills and positions.

Covers paper trading round-trip, rejection handling, kill switch,
slippage bounds, and full pipeline end-to-end through the bridge.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pytest

if TYPE_CHECKING:
    from pathlib import Path

# ── Graceful skip if Phase 2 modules not yet available ────────────────────

try:
    from nyse_ats.execution.nautilus_bridge import (
        MODE_PAPER,
        FillResult,
        NautilusBridge,
    )
    from nyse_ats.storage.corporate_action_log import CorporateActionLog
    from nyse_ats.storage.live_store import LiveStore
    from nyse_core.contracts import (
        Diagnostics,
        PortfolioBuildResult,
        TradePlan,
    )
    from nyse_core.schema import (
        COL_CLOSE,
        COL_DATE,
        COL_SYMBOL,
        RegimeState,
        Side,
    )

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not MODULES_AVAILABLE, reason="Phase 2 modules not yet available"),
]


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_trade_plans(
    symbols: list[str],
    side: Side = Side.BUY,
    shares: int = 100,
) -> list[TradePlan]:
    """Generate a list of TradePlans for the given symbols."""
    now = datetime(2024, 7, 1, 10, 0, 0)
    return [
        TradePlan(
            symbol=sym,
            side=side,
            target_shares=shares,
            current_shares=0,
            order_type="TWAP",
            reason="rebalance",
            decision_timestamp=now,
        )
        for sym in symbols
    ]


def _make_market_prices(symbols: list[str], seed: int = 42) -> dict[str, float]:
    """Generate synthetic market prices for symbols."""
    rng = np.random.default_rng(seed)
    return {sym: round(float(rng.uniform(20, 300)), 2) for sym in symbols}


# ── Tests: Paper Trading Flow ─────────────────────────────────────────────


class TestPaperTradingFlow:
    """End-to-end paper trading execution."""

    def test_trade_plan_to_fill_roundtrip(self, tmp_path: Path) -> None:
        """Create TradePlans -> submit to NautilusBridge(paper) -> verify fills -> reconcile."""
        symbols = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA"]
        plans = _make_trade_plans(symbols, side=Side.BUY, shares=100)
        prices = _make_market_prices(symbols)

        with LiveStore(tmp_path / "live.duckdb") as store:
            bridge = NautilusBridge(
                mode=MODE_PAPER,
                live_store=store,
                rng_seed=42,
            )

            fills, diag = bridge.submit(plans, prices)
            assert not diag.has_errors
            assert len(fills) == len(plans)

            # At least some should succeed (2% rejection rate, seed-dependent)
            successful = [f for f in fills if not f.rejected]
            assert len(successful) >= 3, f"Expected most fills, got {len(successful)}"

            # Reconcile fills to positions
            recon_diag = bridge.reconcile(fills)
            assert not recon_diag.has_errors

            # Verify positions in store
            positions = store.get_current_positions()[0]
            for f in successful:
                assert f.symbol in positions
                assert positions[f.symbol] == f.filled_shares

    def test_rejection_handling(self, tmp_path: Path) -> None:
        """Orders without market prices are rejected; others succeed."""
        symbols = ["AAPL", "MSFT", "GOOG"]
        plans = _make_trade_plans(symbols)
        # Only provide price for AAPL
        prices = {"AAPL": 150.0}

        with LiveStore(tmp_path / "live2.duckdb") as store:
            bridge = NautilusBridge(
                mode=MODE_PAPER,
                live_store=store,
                rng_seed=99,
            )

            fills, diag = bridge.submit(plans, prices)

            # MSFT and GOOG should be rejected (no price)
            rejected = [f for f in fills if f.rejected]
            rejected_syms = {f.symbol for f in rejected}
            assert "MSFT" in rejected_syms
            assert "GOOG" in rejected_syms

            # Reconcile and verify only AAPL has a position
            bridge.reconcile(fills)
            positions = store.get_current_positions()[0]
            assert "MSFT" not in positions
            assert "GOOG" not in positions

    def test_kill_switch_blocks_all(self) -> None:
        """kill_switch=True -> all orders rejected -> zero fills."""
        symbols = ["AAPL", "MSFT"]
        plans = _make_trade_plans(symbols)
        prices = _make_market_prices(symbols)

        bridge = NautilusBridge(mode=MODE_PAPER, kill_switch=True)
        fills, diag = bridge.submit(plans, prices)

        assert len(fills) == len(plans)
        for f in fills:
            assert f.rejected is True
            assert f.rejection_reason == "kill_switch_active"
            assert f.filled_shares == 0

    def test_slippage_within_bounds(self) -> None:
        """Paper mode slippage is realistic (< 20 bps)."""
        symbols = [f"SYM_{i:02d}" for i in range(20)]
        plans = _make_trade_plans(symbols, shares=200)
        prices = _make_market_prices(symbols)

        bridge = NautilusBridge(mode=MODE_PAPER, rng_seed=42)
        fills, _ = bridge.submit(plans, prices)

        successful = [f for f in fills if not f.rejected]
        assert len(successful) > 0

        for f in successful:
            # Max slippage is capped at 5 bps in paper mode
            assert f.slippage_bps <= 20.0, f"{f.symbol}: slippage {f.slippage_bps} bps exceeds 20 bps"
            assert f.slippage_bps >= 0.0

    def test_empty_plans_noop(self) -> None:
        """Empty plan list is a no-op."""
        bridge = NautilusBridge(mode=MODE_PAPER)
        fills, diag = bridge.submit([], {})
        assert fills == []
        assert not diag.has_errors


# ── Tests: Pre-Submit Corporate Action Screening ──────────────────────────


class TestPreSubmitScreening:
    """Corporate action screening filters affected plans."""

    def test_split_detected_cancels_affected_plan(self) -> None:
        """Record split -> pre_submit detects it -> affected plans cancelled."""
        symbols = ["AAPL", "MSFT", "GOOG"]
        plans = _make_trade_plans(symbols)

        # Corporate actions with AAPL split
        actions_df = pd.DataFrame(
            [
                {
                    COL_DATE: date(2024, 7, 1),
                    COL_SYMBOL: "AAPL",
                    "action_type": "SPLIT",
                    "split_ratio": 4.0,
                    "dividend_amount": float("nan"),
                },
            ]
        )

        bridge = NautilusBridge(mode=MODE_PAPER)
        filtered, diag = bridge.pre_submit(plans, actions_df)

        filtered_syms = {tp.symbol for tp in filtered}
        assert "AAPL" not in filtered_syms, "AAPL should be filtered out"
        assert "MSFT" in filtered_syms
        assert "GOOG" in filtered_syms

    def test_no_action_passes_through(self) -> None:
        """No corporate actions -> all plans pass pre_submit unchanged."""
        symbols = ["AAPL", "MSFT"]
        plans = _make_trade_plans(symbols)

        bridge = NautilusBridge(mode=MODE_PAPER)
        filtered, diag = bridge.pre_submit(plans, corporate_actions=None)

        assert len(filtered) == len(plans)
        assert {tp.symbol for tp in filtered} == set(symbols)

    def test_empty_corporate_actions_passes_through(self) -> None:
        """Empty corporate actions DataFrame -> all plans pass."""
        symbols = ["AAPL", "MSFT"]
        plans = _make_trade_plans(symbols)
        empty_ca = pd.DataFrame(columns=[COL_DATE, COL_SYMBOL, "action_type"])

        bridge = NautilusBridge(mode=MODE_PAPER)
        filtered, diag = bridge.pre_submit(plans, empty_ca)

        assert len(filtered) == len(plans)


# ── Tests: Reconciliation ─────────────────────────────────────────────────


class TestReconciliation:
    """Fill reconciliation to LiveStore."""

    def test_reconcile_without_live_store_errors(self) -> None:
        """Reconcile without LiveStore configured -> error diagnostic."""
        bridge = NautilusBridge(mode=MODE_PAPER)
        fills = [
            FillResult(
                symbol="AAPL",
                side="BUY",
                requested_shares=100,
                filled_shares=100,
                fill_price=150.0,
                slippage_bps=2.5,
                fill_timestamp=datetime.now(UTC),
            ),
        ]
        diag = bridge.reconcile(fills)
        assert diag.has_errors

    def test_reconcile_skips_rejected_fills(self, tmp_path: Path) -> None:
        """Rejected fills are not written to LiveStore."""
        with LiveStore(tmp_path / "live.duckdb") as store:
            bridge = NautilusBridge(mode=MODE_PAPER, live_store=store)

            fills = [
                FillResult(
                    symbol="AAPL",
                    side="BUY",
                    requested_shares=100,
                    filled_shares=100,
                    fill_price=150.0,
                    slippage_bps=2.0,
                    fill_timestamp=datetime.now(UTC),
                ),
                FillResult(
                    symbol="MSFT",
                    side="BUY",
                    requested_shares=50,
                    filled_shares=0,
                    fill_price=0.0,
                    slippage_bps=0.0,
                    fill_timestamp=datetime.now(UTC),
                    rejected=True,
                    rejection_reason="no_market_price",
                ),
            ]

            diag = bridge.reconcile(fills)
            assert not diag.has_errors

            positions = store.get_current_positions()[0]
            assert "AAPL" in positions
            assert "MSFT" not in positions

    def test_sell_fills_reduce_positions(self, tmp_path: Path) -> None:
        """Sell fills reduce positions via reconcile."""
        with LiveStore(tmp_path / "live2.duckdb") as store:
            # Pre-load a position via record_fill
            store.record_fill("AAPL", "BUY", 200, 140.0, datetime.now(UTC), 0.0)

            bridge = NautilusBridge(mode=MODE_PAPER, live_store=store)

            fills = [
                FillResult(
                    symbol="AAPL",
                    side="SELL",
                    requested_shares=80,
                    filled_shares=80,
                    fill_price=155.0,
                    slippage_bps=1.5,
                    fill_timestamp=datetime.now(UTC),
                ),
            ]

            diag = bridge.reconcile(fills)
            assert not diag.has_errors

            positions = store.get_current_positions()[0]
            assert positions["AAPL"] == 120  # 200 - 80
