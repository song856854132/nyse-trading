"""Integration tests: full lifecycle of data through DuckDB storage.

Covers OHLCV round-trip, feature versioning, backtest persistence,
upsert semantics, live position tracking, PnL, and corporate action flow.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

# ── Graceful skip if Phase 2 modules not yet available ────────────────────

try:
    from nyse_ats.storage.corporate_action_log import CorporateActionLog
    from nyse_ats.storage.live_store import LiveStore
    from nyse_ats.storage.research_store import ResearchStore
    from nyse_core.contracts import (
        BacktestResult,
        Diagnostics,
        FalsificationCheckResult,
        TradePlan,
    )
    from nyse_core.schema import (
        COL_CLOSE,
        COL_DATE,
        COL_HIGH,
        COL_LOW,
        COL_OPEN,
        COL_SYMBOL,
        COL_VOLUME,
        Severity,
        Side,
    )

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False

from typing import TYPE_CHECKING

from tests.fixtures.synthetic_prices import generate_prices

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not MODULES_AVAILABLE, reason="Phase 2 modules not yet available"),
]


# ── Helpers ────────────────────────────────────────────────────────────────


def _small_ohlcv(n_stocks: int = 5, n_days: int = 30, seed: int = 42) -> pd.DataFrame:
    """Generate a small OHLCV DataFrame for storage tests."""
    return generate_prices(n_stocks=n_stocks, n_days=n_days, seed=seed)


def _make_feature_df(
    symbols: list[str],
    rebalance_date: date,
    factor_names: list[str],
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic long-format feature DataFrame."""
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for sym in symbols:
        for fname in factor_names:
            rows.append(
                {
                    COL_DATE: rebalance_date,
                    COL_SYMBOL: sym,
                    "factor_name": fname,
                    "value": round(float(rng.uniform(0, 1)), 4),
                }
            )
    return pd.DataFrame(rows)


def _make_trade_plan(
    symbol: str,
    side: Side,
    shares: int,
    reason: str = "rebalance",
) -> TradePlan:
    return TradePlan(
        symbol=symbol,
        side=side,
        target_shares=shares,
        current_shares=0,
        order_type="TWAP",
        reason=reason,
        decision_timestamp=datetime(2024, 7, 1, 10, 0, 0),
    )


# ── Tests: ResearchStore ──────────────────────────────────────────────────


class TestResearchStoreLifecycle:
    """End-to-end research data lifecycle."""

    def test_ohlcv_write_read_roundtrip(self, tmp_path: Path) -> None:
        """Write OHLCV DataFrame -> read back -> verify identical."""
        ohlcv = _small_ohlcv(n_stocks=5, n_days=30)
        symbols = sorted(ohlcv[COL_SYMBOL].unique().tolist())
        dates = sorted(ohlcv[COL_DATE].unique().tolist())

        with ResearchStore(tmp_path / "rr.duckdb") as store:
            store_diag = store.store_ohlcv(ohlcv)
            assert not store_diag.has_errors

            loaded, load_diag = store.load_ohlcv(symbols, dates[0], dates[-1])
            assert not load_diag.has_errors
            assert len(loaded) == len(ohlcv)

            # Verify column presence
            for col in [COL_DATE, COL_SYMBOL, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]:
                assert col in loaded.columns

    def test_feature_versioning(self, tmp_path: Path) -> None:
        """Store features for multiple dates -> load specific date -> verify isolation."""
        symbols = [f"SYM_{i:02d}" for i in range(5)]
        date_a = date(2024, 6, 15)
        date_b = date(2024, 7, 15)

        features_a = _make_feature_df(symbols, date_a, ["factor_a", "factor_b"], seed=10)
        features_b = _make_feature_df(symbols, date_b, ["factor_a", "factor_b"], seed=20)

        with ResearchStore(tmp_path / "fv.duckdb") as store:
            store.store_features(features_a, date_a)
            store.store_features(features_b, date_b)

            loaded_a, _ = store.load_features(date_a)
            loaded_b, _ = store.load_features(date_b)

            assert len(loaded_a) == len(features_a)
            assert len(loaded_b) == len(features_b)

            # Values must differ between dates (different seeds)
            vals_a = set(round(v, 4) for v in loaded_a["value"].tolist())
            vals_b = set(round(v, 4) for v in loaded_b["value"].tolist())
            assert vals_a != vals_b, "Features for different dates should differ"

    def test_backtest_result_persistence(self, tmp_path: Path) -> None:
        """Store BacktestResult -> load -> verify all fields preserved."""
        daily_rets = pd.Series(
            np.random.default_rng(42).normal(0.0005, 0.01, 252),
            index=pd.bdate_range("2024-01-02", periods=252, freq="B"),
        )

        original = BacktestResult(
            daily_returns=daily_rets,
            oos_sharpe=1.25,
            oos_cagr=0.12,
            max_drawdown=-0.15,
            annual_turnover=2.4,
            cost_drag_pct=0.8,
            per_fold_sharpe=[1.1, 1.3, 1.35],
            per_factor_contribution={"factor_a": 0.6, "factor_b": 0.4},
            permutation_p_value=0.03,
            bootstrap_ci_lower=0.9,
            bootstrap_ci_upper=1.6,
        )

        run_id = "test-run-001"
        with ResearchStore(tmp_path / "bt.duckdb") as store:
            wr_diag = store.store_backtest_result(original, run_id)
            assert not wr_diag.has_errors

            loaded, ld_diag = store.load_backtest_result(run_id)
            assert not ld_diag.has_errors
            assert loaded is not None

            assert loaded.oos_sharpe == pytest.approx(original.oos_sharpe)
            assert loaded.oos_cagr == pytest.approx(original.oos_cagr)
            assert loaded.max_drawdown == pytest.approx(original.max_drawdown)
            assert loaded.annual_turnover == pytest.approx(original.annual_turnover)
            assert loaded.cost_drag_pct == pytest.approx(original.cost_drag_pct)
            assert loaded.per_fold_sharpe == original.per_fold_sharpe
            assert loaded.per_factor_contribution == original.per_factor_contribution
            assert loaded.permutation_p_value == pytest.approx(original.permutation_p_value)

    def test_upsert_updates_existing(self, tmp_path: Path) -> None:
        """Store OHLCV -> store again with updated prices -> verify latest values."""
        ohlcv = _small_ohlcv(n_stocks=3, n_days=10)
        symbols = sorted(ohlcv[COL_SYMBOL].unique().tolist())
        dates = sorted(ohlcv[COL_DATE].unique().tolist())

        with ResearchStore(tmp_path / "up.duckdb") as store:
            store.store_ohlcv(ohlcv)

            # Update: multiply all close prices by 2
            updated = ohlcv.copy()
            updated[COL_CLOSE] = updated[COL_CLOSE] * 2.0
            store.store_ohlcv(updated)

            loaded, _ = store.load_ohlcv(symbols, dates[0], dates[-1])

            # The loaded close prices should match the doubled values
            loaded_sorted = loaded.sort_values([COL_DATE, COL_SYMBOL]).reset_index(drop=True)
            updated_sorted = updated.sort_values([COL_DATE, COL_SYMBOL]).reset_index(drop=True)

            np.testing.assert_allclose(
                loaded_sorted[COL_CLOSE].values,
                updated_sorted[COL_CLOSE].values,
                rtol=1e-6,
            )

    def test_load_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        """Loading data for symbols not in the store returns an empty DataFrame."""
        with ResearchStore(tmp_path / "empty.duckdb") as store:
            loaded, diag = store.load_ohlcv(
                ["NONEXISTENT"],
                date(2024, 1, 1),
                date(2024, 12, 31),
            )
            assert loaded.empty


# ── Tests: LiveStore ──────────────────────────────────────────────────────


class TestLiveStoreLifecycle:
    """End-to-end live trading state lifecycle."""

    def test_trade_to_fill_to_position(self, tmp_path: Path) -> None:
        """Record fills -> get_current_positions -> verify net position."""
        with LiveStore(tmp_path / "live.duckdb") as store:
            store.record_fill("AAPL", "BUY", 100, 150.0, datetime(2024, 7, 1, 10, 0), 0.0)
            store.record_fill("MSFT", "BUY", 50, 300.0, datetime(2024, 7, 1, 10, 1), 0.0)

            positions, diag = store.get_current_positions()
            assert not diag.has_errors
            assert positions["AAPL"] == 100
            assert positions["MSFT"] == 50

    def test_position_updates_accumulate(self, tmp_path: Path) -> None:
        """Multiple fills for the same symbol accumulate correctly."""
        with LiveStore(tmp_path / "live2.duckdb") as store:
            store.record_fill("AAPL", "BUY", 100, 150.0, datetime(2024, 7, 1, 10, 0), 0.0)
            store.record_fill("AAPL", "BUY", 50, 155.0, datetime(2024, 7, 1, 10, 30), 0.0)

            positions, _ = store.get_current_positions()
            assert positions["AAPL"] == 150

    def test_sell_reduces_position(self, tmp_path: Path) -> None:
        """SELL fills reduce the position correctly."""
        with LiveStore(tmp_path / "live3.duckdb") as store:
            store.record_fill("AAPL", "BUY", 100, 150.0, datetime(2024, 7, 1, 10, 0), 0.0)
            store.record_fill("AAPL", "SELL", 40, 160.0, datetime(2024, 7, 1, 11, 0), 0.0)

            positions, _ = store.get_current_positions()
            assert positions["AAPL"] == 60

    def test_pnl_tracking(self, tmp_path: Path) -> None:
        """Record daily PnL -> retrieve -> verify values match."""
        with LiveStore(tmp_path / "live4.duckdb") as store:
            for day_offset in range(5):
                pnl_date = date(2024, 7, 1) + timedelta(days=day_offset)
                diag = store.record_daily_pnl(
                    pnl_date=pnl_date,
                    gross_return=0.005 + day_offset * 0.001,
                    net_return=0.004 + day_offset * 0.001,
                    cost=0.001,
                )
                assert not diag.has_errors

            result, diag2 = store.get_pnl_history(date(2024, 7, 1), date(2024, 7, 10))
            assert not diag2.has_errors
            assert len(result) == 5

    def test_trade_logging(self, tmp_path: Path) -> None:
        """Record a trade plan and verify it does not raise."""
        with LiveStore(tmp_path / "live5.duckdb") as store:
            plan = _make_trade_plan("AAPL", Side.BUY, 100)
            diag = store.record_trade_plan(plan, date(2024, 7, 1))
            assert not diag.has_errors

    def test_falsification_result_persisted(self, tmp_path: Path) -> None:
        """FalsificationCheckResult stored in LiveStore for audit trail."""
        with LiveStore(tmp_path / "live6.duckdb") as store:
            result = FalsificationCheckResult(
                trigger_id="F1_signal_death",
                trigger_name="Signal IC < 0.01",
                current_value=0.005,
                threshold=0.01,
                severity=Severity.VETO,
                passed=False,
                description="Rolling IC dropped below threshold",
            )
            diag = store.record_falsification_check(result, date(2024, 7, 1))
            assert not diag.has_errors

            rows = store._conn.execute("SELECT trigger_id, passed FROM falsification_checks").fetchall()
            assert len(rows) == 1
            assert rows[0][0] == "F1_signal_death"
            assert rows[0][1] is False

    def test_metrics_logging_and_retrieval(self, tmp_path: Path) -> None:
        """Record PnL metrics -> retrieve history -> verify non-empty."""
        with LiveStore(tmp_path / "live7.duckdb") as store:
            for day_offset in range(5):
                d = date(2024, 7, 1) + timedelta(days=day_offset)
                store.record_daily_pnl(d, 0.005, 0.004, 0.001)

            result, diag = store.get_pnl_history(date(2024, 7, 1), date(2024, 7, 10))
            assert not diag.has_errors
            assert not result.empty


# ── Tests: CorporateActionLog ─────────────────────────────────────────────


class TestCorporateActionFlow:
    """Corporate action detection -> trade plan filtering."""

    def test_split_recorded_and_queryable(self, tmp_path: Path) -> None:
        """Record a stock split -> query it back -> verify details."""
        with CorporateActionLog(tmp_path / "ca.duckdb") as log:
            diag = log.record_action(
                symbol="AAPL",
                action_type="SPLIT",
                action_date=date(2024, 7, 15),
                details={"ratio": 4, "description": "4:1 forward split"},
            )
            assert not diag.has_errors

            actions, diag2 = log.get_actions_since(date(2024, 7, 1))
            assert not diag2.has_errors
            assert len(actions) == 1
            assert actions.iloc[0]["symbol"] == "AAPL"
            assert actions.iloc[0]["action_type"] == "SPLIT"

    def test_pending_actions_for_held_positions(self, tmp_path: Path) -> None:
        """Get pending actions for held symbols -> only matching symbols returned."""
        with CorporateActionLog(tmp_path / "ca2.duckdb") as log:
            log.record_action("AAPL", "SPLIT", date(2024, 8, 1), {"ratio": 2})
            log.record_action("GOOG", "DIVIDEND", date(2024, 8, 5), {"amount": 0.50})
            log.record_action("TSLA", "SPLIT", date(2024, 8, 10), {"ratio": 3})

            pending, diag = log.get_pending_actions(
                held_symbols=["AAPL", "GOOG"],
                since=date(2024, 7, 1),
            )
            assert not diag.has_errors
            symbols_found = set(pending["symbol"].tolist())
            assert symbols_found == {"AAPL", "GOOG"}
            assert "TSLA" not in symbols_found

    def test_no_action_returns_empty(self, tmp_path: Path) -> None:
        """No corporate actions for held symbols -> empty result."""
        with CorporateActionLog(tmp_path / "ca3.duckdb") as log:
            log.record_action("TSLA", "SPLIT", date(2024, 8, 1), {"ratio": 3})

            pending, diag = log.get_pending_actions(
                held_symbols=["AAPL", "MSFT"],
                since=date(2024, 7, 1),
            )
            assert len(pending) == 0

    def test_invalid_action_type_warns(self, tmp_path: Path) -> None:
        """Non-standard action_type produces a warning (append-only, no rejection)."""
        with CorporateActionLog(tmp_path / "ca4.duckdb") as log:
            diag = log.record_action("AAPL", "INVALID", date(2024, 8, 1), {})
            assert diag.has_warnings
            assert not diag.has_errors
