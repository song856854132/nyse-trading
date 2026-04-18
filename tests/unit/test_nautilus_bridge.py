"""Unit tests for nyse_ats.execution.nautilus_bridge."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from nyse_ats.execution.nautilus_bridge import (
    MODE_LIVE,
    MODE_PAPER,
    MODE_SHADOW,
    FillResult,
    NautilusBridge,
)
from nyse_core.contracts import Diagnostics, TradePlan
from nyse_core.schema import Side

# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_plan(
    symbol: str = "AAPL",
    side: Side = Side.BUY,
    shares: int = 100,
    reason: str = "new_entry",
) -> TradePlan:
    """Helper to build a TradePlan for tests."""
    return TradePlan(
        symbol=symbol,
        side=side,
        target_shares=shares,
        current_shares=0,
        order_type="TWAP",
        reason=reason,
        decision_timestamp=datetime(2024, 6, 1, 10, 0, tzinfo=UTC),
    )


@pytest.fixture()
def paper_bridge() -> NautilusBridge:
    """Deterministic paper bridge (seed=42 avoids random rejection)."""
    return NautilusBridge(mode=MODE_PAPER, rng_seed=42)


@pytest.fixture()
def shadow_bridge() -> NautilusBridge:
    return NautilusBridge(mode=MODE_SHADOW)


@pytest.fixture()
def mock_live_store() -> MagicMock:
    store = MagicMock()
    store.record_fill = MagicMock(return_value=Diagnostics())
    return store


# ── Construction ────────────────────────────────────────────────────────────


class TestBridgeConstruction:
    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid mode"):
            NautilusBridge(mode="turbo")

    def test_valid_modes(self) -> None:
        for m in (MODE_PAPER, MODE_SHADOW, MODE_LIVE):
            bridge = NautilusBridge(mode=m)
            assert bridge._mode == m


# ── Paper mode: submit ──────────────────────────────────────────────────────


class TestPaperSubmit:
    def test_successful_fill(self, paper_bridge: NautilusBridge) -> None:
        plans = [_make_plan("AAPL", Side.BUY, 100)]
        fills, diag = paper_bridge.submit(plans, {"AAPL": 150.0})

        assert len(fills) == 1
        f = fills[0]
        assert isinstance(f, FillResult)
        assert f.symbol == "AAPL"
        assert f.side == "BUY"
        assert f.filled_shares == 100
        assert not f.rejected
        assert not diag.has_errors

    def test_slippage_within_bounds(self, paper_bridge: NautilusBridge) -> None:
        plans = [_make_plan("MSFT", Side.BUY, 50)]
        fills, _ = paper_bridge.submit(plans, {"MSFT": 400.0})

        f = fills[0]
        assert 0.0 <= f.slippage_bps <= 5.0
        # Buy slippage means fill_price >= market_price
        assert f.fill_price >= 400.0

    def test_sell_slippage_direction(self) -> None:
        bridge = NautilusBridge(mode=MODE_PAPER, rng_seed=99)
        plans = [_make_plan("GOOG", Side.SELL, 30)]
        fills, _ = bridge.submit(plans, {"GOOG": 170.0})

        f = fills[0]
        # Sell slippage means fill_price <= market_price
        assert f.fill_price <= 170.0

    def test_no_market_price_rejected(self, paper_bridge: NautilusBridge) -> None:
        plans = [_make_plan("UNKNOWN")]
        fills, diag = paper_bridge.submit(plans, {})

        assert len(fills) == 1
        assert fills[0].rejected
        assert fills[0].rejection_reason == "no_market_price"
        assert diag.has_warnings

    def test_empty_plan_list(self, paper_bridge: NautilusBridge) -> None:
        fills, diag = paper_bridge.submit([], {"AAPL": 150.0})
        assert fills == []
        assert not diag.has_errors

    def test_multiple_plans(self) -> None:
        bridge = NautilusBridge(mode=MODE_PAPER, rng_seed=12345)
        plans = [
            _make_plan("AAPL", Side.BUY, 100),
            _make_plan("MSFT", Side.SELL, 50),
            _make_plan("GOOG", Side.BUY, 200),
        ]
        prices = {"AAPL": 150.0, "MSFT": 400.0, "GOOG": 170.0}
        fills, diag = bridge.submit(plans, prices)

        assert len(fills) == 3
        symbols = {f.symbol for f in fills}
        assert symbols == {"AAPL", "MSFT", "GOOG"}


# ── Kill switch ─────────────────────────────────────────────────────────────


class TestKillSwitch:
    def test_rejects_all_orders(self) -> None:
        bridge = NautilusBridge(mode=MODE_PAPER, kill_switch=True, rng_seed=1)
        plans = [
            _make_plan("AAPL"),
            _make_plan("MSFT"),
        ]
        fills, diag = bridge.submit(plans, {"AAPL": 150.0, "MSFT": 400.0})

        assert len(fills) == 2
        assert all(f.rejected for f in fills)
        assert all(f.rejection_reason == "kill_switch_active" for f in fills)
        assert all(f.filled_shares == 0 for f in fills)
        assert diag.has_warnings


# ── Shadow mode ─────────────────────────────────────────────────────────────


class TestShadowSubmit:
    def test_tracks_prices_no_fills(self, shadow_bridge: NautilusBridge) -> None:
        plans = [_make_plan("AAPL")]
        fills, diag = shadow_bridge.submit(plans, {"AAPL": 150.0})

        assert len(fills) == 1
        f = fills[0]
        assert f.filled_shares == 0  # Shadow never fills
        assert f.fill_price == 150.0
        assert not f.rejected
        assert not diag.has_errors

    def test_missing_price_still_tracks(self, shadow_bridge: NautilusBridge) -> None:
        plans = [_make_plan("MISSING")]
        fills, _ = shadow_bridge.submit(plans, {})
        assert len(fills) == 1
        assert fills[0].fill_price == 0.0

    def test_shadow_fills_have_is_shadow_true(self, shadow_bridge: NautilusBridge) -> None:
        """Shadow fills must set is_shadow=True to prevent phantom live records."""
        plans = [_make_plan("AAPL"), _make_plan("MSFT")]
        fills, _ = shadow_bridge.submit(plans, {"AAPL": 150.0, "MSFT": 400.0})

        assert len(fills) == 2
        assert all(f.is_shadow for f in fills)

    def test_paper_fills_have_is_shadow_false(self, paper_bridge: NautilusBridge) -> None:
        """Paper fills must NOT have is_shadow set."""
        plans = [_make_plan("AAPL")]
        fills, _ = paper_bridge.submit(plans, {"AAPL": 150.0})

        assert len(fills) == 1
        assert not fills[0].is_shadow


# ── Live mode ───────────────────────────────────────────────────────────────


class TestLiveMode:
    def test_raises_not_implemented(self) -> None:
        bridge = NautilusBridge(mode=MODE_LIVE)
        with pytest.raises(NotImplementedError, match="NautilusTrader"):
            bridge.submit([_make_plan()], {"AAPL": 150.0})


# ── Pre-submit: corporate actions ───────────────────────────────────────────


class TestPreSubmit:
    def test_no_corporate_actions_passes_through(self, paper_bridge: NautilusBridge) -> None:
        plans = [_make_plan("AAPL"), _make_plan("MSFT")]
        filtered, diag = paper_bridge.pre_submit(plans, None)
        assert len(filtered) == 2
        assert not diag.has_errors

    def test_empty_ca_dataframe_passes_through(self, paper_bridge: NautilusBridge) -> None:
        plans = [_make_plan("AAPL")]
        empty_ca = pd.DataFrame(columns=["date", "symbol", "action_type"])
        filtered, diag = paper_bridge.pre_submit(plans, empty_ca)
        assert len(filtered) == 1

    def test_corporate_action_cancels_affected_plan(self, paper_bridge: NautilusBridge) -> None:
        plans = [_make_plan("AAPL"), _make_plan("MSFT")]
        ca = pd.DataFrame(
            {
                "date": [datetime(2024, 6, 1).date()],
                "symbol": ["AAPL"],
                "action_type": ["split"],
            }
        )
        filtered, diag = paper_bridge.pre_submit(plans, ca)

        symbols = [tp.symbol for tp in filtered]
        assert "AAPL" not in symbols
        assert "MSFT" in symbols
        assert diag.has_warnings

    def test_empty_plan_list(self, paper_bridge: NautilusBridge) -> None:
        filtered, diag = paper_bridge.pre_submit([], None)
        assert filtered == []
        assert not diag.has_errors


# ── Reconcile ───────────────────────────────────────────────────────────────


class TestReconcile:
    def test_writes_fills_to_live_store(self, mock_live_store: MagicMock) -> None:
        bridge = NautilusBridge(mode=MODE_PAPER, live_store=mock_live_store, rng_seed=1)
        fills = [
            FillResult(
                symbol="AAPL",
                side="BUY",
                requested_shares=100,
                filled_shares=100,
                fill_price=150.05,
                slippage_bps=2.0,
                fill_timestamp=datetime.now(UTC),
            ),
        ]
        diag = bridge.reconcile(fills)

        mock_live_store.record_fill.assert_called_once()
        call_kwargs = mock_live_store.record_fill.call_args
        assert call_kwargs.kwargs["symbol"] == "AAPL"
        assert call_kwargs.kwargs["side"] == "BUY"
        assert call_kwargs.kwargs["filled_shares"] == 100
        assert not diag.has_errors

    def test_sell_reconcile_records_sell(self, mock_live_store: MagicMock) -> None:
        bridge = NautilusBridge(mode=MODE_PAPER, live_store=mock_live_store, rng_seed=1)
        fills = [
            FillResult(
                symbol="MSFT",
                side="SELL",
                requested_shares=50,
                filled_shares=50,
                fill_price=399.80,
                slippage_bps=1.5,
                fill_timestamp=datetime.now(UTC),
            ),
        ]
        bridge.reconcile(fills)

        mock_live_store.record_fill.assert_called_once()
        call_kwargs = mock_live_store.record_fill.call_args
        assert call_kwargs.kwargs["symbol"] == "MSFT"
        assert call_kwargs.kwargs["side"] == "SELL"
        assert call_kwargs.kwargs["filled_shares"] == 50

    def test_skips_rejected_fills(self, mock_live_store: MagicMock) -> None:
        bridge = NautilusBridge(mode=MODE_PAPER, live_store=mock_live_store, rng_seed=1)
        fills = [
            FillResult(
                symbol="BAD",
                side="BUY",
                requested_shares=100,
                filled_shares=0,
                fill_price=0.0,
                slippage_bps=0.0,
                fill_timestamp=datetime.now(UTC),
                rejected=True,
                rejection_reason="no_market_price",
            ),
        ]
        diag = bridge.reconcile(fills)

        mock_live_store.record_fill.assert_not_called()
        assert not diag.has_errors

    def test_skips_shadow_fills(self, mock_live_store: MagicMock) -> None:
        """Shadow fills (is_shadow=True) must NOT be written to live_store."""
        bridge = NautilusBridge(
            mode=MODE_SHADOW,
            live_store=mock_live_store,
        )
        fills = [
            FillResult(
                symbol="AAPL",
                side="BUY",
                requested_shares=100,
                filled_shares=0,
                fill_price=150.0,
                slippage_bps=0.0,
                fill_timestamp=datetime.now(UTC),
                is_shadow=True,
            ),
        ]
        diag = bridge.reconcile(fills)

        mock_live_store.record_fill.assert_not_called()
        assert not diag.has_errors

    def test_mixed_fills_only_records_non_shadow(self, mock_live_store: MagicMock) -> None:
        """Only real (non-shadow, non-rejected) fills go to live_store."""
        bridge = NautilusBridge(mode=MODE_PAPER, live_store=mock_live_store, rng_seed=1)
        now = datetime.now(UTC)
        fills = [
            FillResult(
                symbol="AAPL",
                side="BUY",
                requested_shares=100,
                filled_shares=100,
                fill_price=150.0,
                slippage_bps=2.0,
                fill_timestamp=now,
            ),
            FillResult(
                symbol="SPY",
                side="BUY",
                requested_shares=50,
                filled_shares=0,
                fill_price=450.0,
                slippage_bps=0.0,
                fill_timestamp=now,
                is_shadow=True,
            ),
            FillResult(
                symbol="BAD",
                side="BUY",
                requested_shares=100,
                filled_shares=0,
                fill_price=0.0,
                slippage_bps=0.0,
                fill_timestamp=now,
                rejected=True,
                rejection_reason="no_market_price",
            ),
        ]
        bridge.reconcile(fills)

        # Only AAPL should be recorded
        assert mock_live_store.record_fill.call_count == 1
        call_kwargs = mock_live_store.record_fill.call_args.kwargs
        assert call_kwargs["symbol"] == "AAPL"

    def test_no_live_store_logs_error(self) -> None:
        bridge = NautilusBridge(mode=MODE_PAPER)
        fills = [
            FillResult(
                symbol="AAPL",
                side="BUY",
                requested_shares=100,
                filled_shares=100,
                fill_price=150.0,
                slippage_bps=1.0,
                fill_timestamp=datetime.now(UTC),
            ),
        ]
        diag = bridge.reconcile(fills)
        assert diag.has_errors
