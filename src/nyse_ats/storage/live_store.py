"""DuckDB storage for live trading state.

Manages the ``live.duckdb`` database which holds:
- Trade plans submitted by the portfolio builder
- Execution fills from the broker
- Current positions (materialised from fills)
- Daily P&L records
- Falsification check results

WAL mode is enabled for concurrent dashboard reads.
All public methods return ``Diagnostics`` or ``(result, Diagnostics)`` tuples.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import duckdb
import pandas as pd

from nyse_core.contracts import Diagnostics, FalsificationCheckResult, TradePlan

if TYPE_CHECKING:
    from datetime import date, datetime
    from pathlib import Path

logger = logging.getLogger(__name__)

_SRC = "storage.live_store"

# ── DDL ──────────────────────────────────────────────────────────────────────

_TRADE_PLANS_DDL = """
CREATE TABLE IF NOT EXISTS trade_plans (
    id                  INTEGER PRIMARY KEY DEFAULT(nextval('trade_plan_seq')),
    rebalance_date      DATE NOT NULL,
    symbol              VARCHAR NOT NULL,
    side                VARCHAR NOT NULL,
    target_shares       INTEGER NOT NULL,
    current_shares      INTEGER NOT NULL,
    order_type          VARCHAR NOT NULL,
    reason              VARCHAR NOT NULL,
    decision_timestamp  TIMESTAMP NOT NULL,
    execution_timestamp TIMESTAMP,
    estimated_cost_bps  DOUBLE NOT NULL DEFAULT 0.0,
    recorded_at         TIMESTAMP NOT NULL DEFAULT current_timestamp
);
"""

_FILLS_DDL = """
CREATE TABLE IF NOT EXISTS fills (
    id             INTEGER PRIMARY KEY DEFAULT(nextval('fill_seq')),
    symbol         VARCHAR NOT NULL,
    side           VARCHAR NOT NULL,
    filled_shares  INTEGER NOT NULL,
    fill_price     DOUBLE NOT NULL,
    fill_timestamp TIMESTAMP NOT NULL,
    slippage_bps   DOUBLE NOT NULL DEFAULT 0.0,
    recorded_at    TIMESTAMP NOT NULL DEFAULT current_timestamp
);
"""

_DAILY_PNL_DDL = """
CREATE TABLE IF NOT EXISTS daily_pnl (
    date         DATE PRIMARY KEY,
    gross_return DOUBLE NOT NULL,
    net_return   DOUBLE NOT NULL,
    cost         DOUBLE NOT NULL
);
"""

_FALSIFICATION_DDL = """
CREATE TABLE IF NOT EXISTS falsification_checks (
    id             INTEGER PRIMARY KEY DEFAULT(nextval('fcheck_seq')),
    check_date     DATE NOT NULL,
    trigger_id     VARCHAR NOT NULL,
    trigger_name   VARCHAR NOT NULL,
    current_value  DOUBLE NOT NULL,
    threshold      DOUBLE NOT NULL,
    severity       VARCHAR NOT NULL,
    passed         BOOLEAN NOT NULL,
    description    VARCHAR NOT NULL,
    recorded_at    TIMESTAMP NOT NULL DEFAULT current_timestamp
);
"""


class LiveStore:
    """DuckDB-backed store for live trading state.

    WAL mode is enabled so dashboard readers can access the database
    concurrently with the trading engine writer.

    Args:
        db_path: Path to the DuckDB database file.  Use ``Path(":memory:")``
                 for an ephemeral in-memory database (useful for tests).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(db_path))
        self._enable_wal()
        self._create_sequences()
        self._create_tables()
        logger.info("LiveStore initialized (WAL): %s", db_path)

    def _enable_wal(self) -> None:
        """Enable WAL journal mode for concurrent read access."""
        # Not all DuckDB builds support every pragma; suppress silently.
        with contextlib.suppress(Exception):
            self._conn.execute("PRAGMA enable_checkpoint_on_shutdown")

    def _create_sequences(self) -> None:
        for seq in ("trade_plan_seq", "fill_seq", "fcheck_seq"):
            self._conn.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq} START 1")

    def _create_tables(self) -> None:
        self._conn.execute(_TRADE_PLANS_DDL)
        self._conn.execute(_FILLS_DDL)
        self._conn.execute(_DAILY_PNL_DDL)
        self._conn.execute(_FALSIFICATION_DDL)

    # ── Trade Plans ──────────────────────────────────────────────────────────

    def record_trade_plan(self, plan: TradePlan, rebalance_date: date) -> Diagnostics:
        """Record a single trade plan from a rebalance cycle."""
        diag = Diagnostics()
        try:
            self._conn.execute(
                """
                INSERT INTO trade_plans
                    (rebalance_date, symbol, side, target_shares, current_shares,
                     order_type, reason, decision_timestamp, execution_timestamp,
                     estimated_cost_bps)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                [
                    str(rebalance_date),
                    plan.symbol,
                    plan.side.value,
                    plan.target_shares,
                    plan.current_shares,
                    plan.order_type,
                    plan.reason,
                    plan.decision_timestamp,
                    plan.execution_timestamp,
                    plan.estimated_cost_bps,
                ],
            )
            diag.info(_SRC, f"Recorded trade plan: {plan.symbol} {plan.side.value}")
        except Exception as exc:
            diag.error(_SRC, f"Trade plan write failed: {exc}")
        return diag

    # ── Fills ────────────────────────────────────────────────────────────────

    def record_fill(
        self,
        symbol: str,
        side: str,
        filled_shares: int,
        fill_price: float,
        fill_timestamp: datetime,
        slippage_bps: float,
    ) -> Diagnostics:
        """Record an execution fill from the broker."""
        diag = Diagnostics()
        if side not in ("BUY", "SELL"):
            diag.error(_SRC, f"Invalid side '{side}' — must be BUY or SELL")
            return diag
        try:
            self._conn.execute(
                """
                INSERT INTO fills
                    (symbol, side, filled_shares, fill_price, fill_timestamp, slippage_bps)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                [symbol, side, filled_shares, fill_price, fill_timestamp, slippage_bps],
            )
            diag.info(_SRC, f"Recorded fill: {symbol} {side} {filled_shares}@{fill_price:.2f}")
        except Exception as exc:
            diag.error(_SRC, f"Fill write failed: {exc}")
        return diag

    # ── Positions ────────────────────────────────────────────────────────────

    def get_current_positions(self) -> tuple[dict[str, int], Diagnostics]:
        """Aggregate all fills to compute net position per symbol.

        BUY adds shares, SELL subtracts shares.  Symbols with net 0 are excluded.
        """
        diag = Diagnostics()
        try:
            rows = self._conn.execute(
                """
                SELECT symbol,
                       SUM(CASE WHEN side = 'BUY' THEN filled_shares
                                WHEN side = 'SELL' THEN -filled_shares
                                ELSE 0 END) AS net_shares
                FROM fills
                GROUP BY symbol
                HAVING net_shares != 0
                ORDER BY symbol
                """
            ).fetchall()
            positions = {row[0]: int(row[1]) for row in rows}
            diag.info(_SRC, f"Current positions: {len(positions)} symbols")
            return positions, diag
        except Exception as exc:
            diag.error(_SRC, f"Position aggregation failed: {exc}")
            return {}, diag

    def get_position_weights(self, portfolio_value: float) -> tuple[dict[str, float], Diagnostics]:
        """Compute position weights as fraction of portfolio value.

        Weight = (net_shares * latest_fill_price) / portfolio_value.
        """
        diag = Diagnostics()

        if portfolio_value <= 0:
            diag.error(_SRC, f"Invalid portfolio value: {portfolio_value}")
            return {}, diag

        try:
            rows = self._conn.execute(
                """
                WITH net AS (
                    SELECT symbol,
                           SUM(CASE WHEN side = 'BUY' THEN filled_shares
                                    WHEN side = 'SELL' THEN -filled_shares
                                    ELSE 0 END) AS net_shares
                    FROM fills
                    GROUP BY symbol
                    HAVING net_shares != 0
                ),
                latest_price AS (
                    SELECT symbol, fill_price,
                           ROW_NUMBER() OVER (
                               PARTITION BY symbol ORDER BY fill_timestamp DESC
                           ) AS rn
                    FROM fills
                )
                SELECT n.symbol,
                       n.net_shares * lp.fill_price AS market_value
                FROM net n
                JOIN latest_price lp ON n.symbol = lp.symbol AND lp.rn = 1
                ORDER BY n.symbol
                """
            ).fetchall()
            weights = {row[0]: row[1] / portfolio_value for row in rows}
            diag.info(_SRC, f"Position weights: {len(weights)} symbols")
            return weights, diag
        except Exception as exc:
            diag.error(_SRC, f"Weight calculation failed: {exc}")
            return {}, diag

    # ── Daily P&L ────────────────────────────────────────────────────────────

    def record_daily_pnl(
        self,
        pnl_date: date,
        gross_return: float,
        net_return: float,
        cost: float,
    ) -> Diagnostics:
        """Record or replace one day's P&L figures."""
        diag = Diagnostics()
        try:
            self._conn.execute(
                """
                INSERT INTO daily_pnl (date, gross_return, net_return, cost)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (date) DO UPDATE SET
                    gross_return = EXCLUDED.gross_return,
                    net_return = EXCLUDED.net_return,
                    cost = EXCLUDED.cost
                """,
                [str(pnl_date), gross_return, net_return, cost],
            )
            diag.info(_SRC, f"Recorded daily P&L for {pnl_date}")
        except Exception as exc:
            diag.error(_SRC, f"P&L write failed: {exc}")
        return diag

    def get_pnl_history(self, start: date, end: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Read daily P&L records for the given date range."""
        diag = Diagnostics()
        empty = pd.DataFrame(columns=["date", "gross_return", "net_return", "cost"])

        try:
            result = self._conn.execute(
                """
                SELECT date, gross_return, net_return, cost
                FROM daily_pnl
                WHERE date >= $1::DATE AND date <= $2::DATE
                ORDER BY date
                """,
                [str(start), str(end)],
            ).fetchdf()
            diag.info(_SRC, f"Loaded {len(result)} P&L rows")
            return result, diag
        except Exception as exc:
            diag.error(_SRC, f"P&L read failed: {exc}")
            return empty, diag

    # ── Falsification Checks ─────────────────────────────────────────────────

    def record_falsification_check(
        self,
        result: FalsificationCheckResult,
        check_date: date,
    ) -> Diagnostics:
        """Record a single falsification check result."""
        diag = Diagnostics()
        try:
            self._conn.execute(
                """
                INSERT INTO falsification_checks
                    (check_date, trigger_id, trigger_name, current_value,
                     threshold, severity, passed, description)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                [
                    str(check_date),
                    result.trigger_id,
                    result.trigger_name,
                    result.current_value,
                    result.threshold,
                    result.severity.value,
                    result.passed,
                    result.description,
                ],
            )
            diag.info(
                _SRC,
                f"Recorded falsification check: {result.trigger_id} passed={result.passed}",
            )
        except Exception as exc:
            diag.error(_SRC, f"Falsification check write failed: {exc}")
        return diag

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.info("LiveStore closed: %s", self._db_path)

    def __enter__(self) -> LiveStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
