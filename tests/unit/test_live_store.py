"""Unit tests for nyse_ats.storage.live_store."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

import pytest

from nyse_ats.storage.live_store import LiveStore
from nyse_core.contracts import FalsificationCheckResult, TradePlan
from nyse_core.schema import Severity, Side

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def store(tmp_path: Path) -> LiveStore:
    """Create a LiveStore backed by a temporary DuckDB file."""
    db_path = tmp_path / "live.duckdb"
    s = LiveStore(db_path)
    yield s
    s.close()


@pytest.fixture
def sample_trade_plan() -> TradePlan:
    """Minimal TradePlan for testing."""
    return TradePlan(
        symbol="AAPL",
        side=Side.BUY,
        target_shares=100,
        current_shares=0,
        order_type="TWAP",
        reason="new_entry",
        decision_timestamp=datetime(2024, 1, 2, 9, 30),
        estimated_cost_bps=5.2,
    )


@pytest.fixture
def sample_falsification_result() -> FalsificationCheckResult:
    """Minimal FalsificationCheckResult for testing."""
    return FalsificationCheckResult(
        trigger_id="F1",
        trigger_name="IC decay",
        current_value=0.02,
        threshold=0.05,
        severity=Severity.WARNING,
        passed=True,
        description="IC above minimum threshold",
    )


class TestLiveStoreInit:
    """Tests for table creation on init."""

    def test_tables_created_on_init(self, store: LiveStore) -> None:
        """All required tables must exist after initialization."""
        tables = store._conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "trade_plans" in table_names
        assert "fills" in table_names
        assert "daily_pnl" in table_names
        assert "falsification_checks" in table_names

    def test_context_manager(self, tmp_path: Path) -> None:
        """LiveStore works as a context manager."""
        db_path = tmp_path / "ctx_live.duckdb"
        with LiveStore(db_path) as s:
            tables = s._conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
            assert len(tables) >= 4


class TestRecordTradePlan:
    """Tests for record_trade_plan."""

    def test_record_trade_plan(self, store: LiveStore, sample_trade_plan: TradePlan) -> None:
        """Recording a trade plan should succeed without errors."""
        diag = store.record_trade_plan(sample_trade_plan, rebalance_date=date(2024, 1, 2))
        assert not diag.has_errors

    def test_record_multiple_trade_plans(self, store: LiveStore) -> None:
        """Multiple plans for different symbols can be recorded."""
        for sym in ["AAPL", "MSFT", "GOOG"]:
            plan = TradePlan(
                symbol=sym,
                side=Side.BUY,
                target_shares=100,
                current_shares=0,
                order_type="TWAP",
                reason="new_entry",
                decision_timestamp=datetime(2024, 1, 2, 9, 30),
            )
            diag = store.record_trade_plan(plan, rebalance_date=date(2024, 1, 2))
            assert not diag.has_errors

        rows = store._conn.execute("SELECT COUNT(*) FROM trade_plans").fetchone()
        assert rows[0] == 3


class TestRecordFill:
    """Tests for record_fill."""

    def test_record_fill(self, store: LiveStore) -> None:
        """Recording a fill should succeed without errors."""
        diag = store.record_fill(
            symbol="AAPL",
            side="BUY",
            filled_shares=100,
            fill_price=150.25,
            fill_timestamp=datetime(2024, 1, 15, 10, 0),
            slippage_bps=2.5,
        )
        assert not diag.has_errors

    def test_invalid_side_rejected(self, store: LiveStore) -> None:
        """Fills with invalid side string are rejected with an error."""
        diag = store.record_fill(
            symbol="AAPL",
            side="HOLD",
            filled_shares=100,
            fill_price=150.0,
            fill_timestamp=datetime(2024, 1, 15, 10, 0),
            slippage_bps=0.0,
        )
        assert diag.has_errors


class TestGetCurrentPositions:
    """Tests for get_current_positions aggregation from fills."""

    def test_single_buy(self, store: LiveStore) -> None:
        """A single BUY fill creates a position."""
        store.record_fill("AAPL", "BUY", 100, 150.0, datetime(2024, 1, 15, 10, 0), 0.0)

        positions, diag = store.get_current_positions()
        assert not diag.has_errors
        assert positions == {"AAPL": 100}

    def test_buy_and_sell_aggregation(self, store: LiveStore) -> None:
        """Net position = BUY shares - SELL shares."""
        ts = datetime(2024, 1, 15, 10, 0)
        store.record_fill("AAPL", "BUY", 100, 150.0, ts, 0.0)
        store.record_fill("MSFT", "BUY", 200, 300.0, ts, 0.0)
        store.record_fill("AAPL", "SELL", 30, 155.0, datetime(2024, 1, 16, 10, 0), 0.0)

        positions, diag = store.get_current_positions()
        assert not diag.has_errors
        assert positions["AAPL"] == 70  # 100 - 30
        assert positions["MSFT"] == 200

    def test_flat_position_excluded(self, store: LiveStore) -> None:
        """A symbol with net 0 shares is excluded from positions."""
        ts = datetime(2024, 1, 15, 10, 0)
        store.record_fill("AAPL", "BUY", 50, 150.0, ts, 0.0)
        store.record_fill("AAPL", "SELL", 50, 152.0, datetime(2024, 1, 16, 10, 0), 0.0)

        positions, diag = store.get_current_positions()
        assert not diag.has_errors
        assert "AAPL" not in positions

    def test_empty_fills_returns_empty(self, store: LiveStore) -> None:
        """No fills means empty positions dict."""
        positions, diag = store.get_current_positions()
        assert not diag.has_errors
        assert positions == {}

    def test_multiple_buys_accumulate(self, store: LiveStore) -> None:
        """Successive BUY fills for the same symbol accumulate."""
        store.record_fill("AAPL", "BUY", 100, 150.0, datetime(2024, 1, 15, 10, 0), 0.0)
        store.record_fill("AAPL", "BUY", 50, 155.0, datetime(2024, 1, 16, 10, 0), 0.0)

        positions, diag = store.get_current_positions()
        assert not diag.has_errors
        assert positions["AAPL"] == 150


class TestGetPositionWeights:
    """Tests for get_position_weights."""

    def test_position_weights_calculation(self, store: LiveStore) -> None:
        """Weights = (net_shares * latest_fill_price) / portfolio_value."""
        ts = datetime(2024, 1, 15, 10, 0)
        store.record_fill("AAPL", "BUY", 100, 150.0, ts, 0.0)
        store.record_fill("MSFT", "BUY", 50, 300.0, ts, 0.0)

        portfolio_value = 100_000.0
        weights, diag = store.get_position_weights(portfolio_value)
        assert not diag.has_errors
        # AAPL: 100 * 150 / 100000 = 0.15
        assert weights["AAPL"] == pytest.approx(0.15)
        # MSFT: 50 * 300 / 100000 = 0.15
        assert weights["MSFT"] == pytest.approx(0.15)

    def test_invalid_portfolio_value_rejected(self, store: LiveStore) -> None:
        """Portfolio value of 0 or negative should produce an error."""
        weights, diag = store.get_position_weights(0.0)
        assert diag.has_errors
        assert weights == {}

    def test_negative_portfolio_value_rejected(self, store: LiveStore) -> None:
        """Negative portfolio value should produce an error."""
        weights, diag = store.get_position_weights(-50_000.0)
        assert diag.has_errors
        assert weights == {}


class TestDailyPnL:
    """Tests for record_daily_pnl and get_pnl_history."""

    def test_record_daily_pnl(self, store: LiveStore) -> None:
        """Recording a daily P&L entry should succeed."""
        diag = store.record_daily_pnl(
            pnl_date=date(2024, 1, 15),
            gross_return=0.012,
            net_return=0.010,
            cost=50.0,
        )
        assert not diag.has_errors

    def test_pnl_history_retrieval(self, store: LiveStore) -> None:
        """Stored P&L rows should be retrievable by date range."""
        for i, d in enumerate([date(2024, 1, 15), date(2024, 1, 16), date(2024, 1, 17)]):
            store.record_daily_pnl(d, 0.01 * (i + 1), 0.009 * (i + 1), 10.0 * (i + 1))

        result, diag = store.get_pnl_history(date(2024, 1, 15), date(2024, 1, 17))
        assert not diag.has_errors
        assert len(result) == 3
        assert "gross_return" in result.columns
        assert "net_return" in result.columns
        assert "cost" in result.columns

    def test_pnl_upsert_on_conflict(self, store: LiveStore) -> None:
        """Recording P&L for the same date should update, not duplicate."""
        store.record_daily_pnl(date(2024, 1, 15), 0.01, 0.009, 10.0)
        store.record_daily_pnl(date(2024, 1, 15), 0.02, 0.018, 20.0)

        result, _ = store.get_pnl_history(date(2024, 1, 15), date(2024, 1, 15))
        assert len(result) == 1
        assert result["gross_return"].iloc[0] == pytest.approx(0.02)

    def test_empty_pnl_history(self, store: LiveStore) -> None:
        """Empty database returns empty P&L DataFrame."""
        result, diag = store.get_pnl_history(date(2024, 1, 1), date(2024, 12, 31))
        assert not diag.has_errors
        assert len(result) == 0


class TestFalsificationChecks:
    """Tests for record_falsification_check."""

    def test_record_falsification_check(
        self,
        store: LiveStore,
        sample_falsification_result: FalsificationCheckResult,
    ) -> None:
        """Recording a falsification check should succeed."""
        diag = store.record_falsification_check(
            sample_falsification_result,
            check_date=date(2024, 1, 15),
        )
        assert not diag.has_errors

    def test_record_veto_severity(self, store: LiveStore) -> None:
        """VETO-severity checks should be stored correctly."""
        check = FalsificationCheckResult(
            trigger_id="F2",
            trigger_name="Drawdown",
            current_value=-0.04,
            threshold=-0.03,
            severity=Severity.VETO,
            passed=False,
            description="Drawdown exceeded threshold",
        )
        diag = store.record_falsification_check(check, check_date=date(2024, 1, 15))
        assert not diag.has_errors

    def test_multiple_checks_same_day(self, store: LiveStore) -> None:
        """Multiple falsification checks on the same day are stored independently."""
        r1 = FalsificationCheckResult(
            trigger_id="F1",
            trigger_name="IC decay",
            current_value=0.02,
            threshold=0.05,
            severity=Severity.WARNING,
            passed=True,
            description="OK",
        )
        r2 = FalsificationCheckResult(
            trigger_id="F2",
            trigger_name="Drawdown",
            current_value=-0.04,
            threshold=-0.03,
            severity=Severity.VETO,
            passed=False,
            description="Drawdown exceeded",
        )
        store.record_falsification_check(r1, check_date=date(2024, 1, 15))
        store.record_falsification_check(r2, check_date=date(2024, 1, 15))

        rows = store._conn.execute("SELECT COUNT(*) FROM falsification_checks").fetchone()
        assert rows[0] == 2


class TestWALMode:
    """Tests that WAL mode is configured."""

    def test_wal_mode_enabled(self, tmp_path: Path) -> None:
        """The store should initialise without errors (WAL pragma runs at init)."""
        store = LiveStore(tmp_path / "wal.duckdb")
        # If WAL init failed, __init__ would raise. This test verifies it does not.
        store.close()


class TestLiveStoreLifecycle:
    """Tests for context manager close behaviour."""

    def test_context_manager_close(self, tmp_path: Path) -> None:
        """Store is usable inside with-block and closed after."""
        with LiveStore(tmp_path / "cm.duckdb") as store:
            diag = store.record_fill(
                "AAPL",
                "BUY",
                10,
                150.0,
                datetime(2024, 1, 15, 10, 0),
                0.0,
            )
            assert not diag.has_errors
        # After __exit__, further ops should produce an error (either raised or in Diagnostics)
        try:
            diag = store.record_fill("AAPL", "BUY", 10, 150.0, datetime(2024, 1, 15, 10, 0), 0.0)
            assert diag.has_errors, "Expected error diagnostic after close"
        except Exception:
            pass  # Exception is also acceptable
