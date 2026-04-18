"""Append-only event log for corporate actions (splits, dividends).

Event-sourced design: rows are NEVER updated or deleted. Each row is an
immutable event recording a corporate action that was observed. Downstream
consumers replay events to derive current state.

All public methods return ``Diagnostics`` or ``(result, Diagnostics)`` tuples.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import duckdb
import pandas as pd

from nyse_core.contracts import Diagnostics

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

logger = logging.getLogger(__name__)

_SRC = "storage.corporate_action_log"

_CA_DDL = """
CREATE TABLE IF NOT EXISTS corporate_actions (
    id          INTEGER PRIMARY KEY DEFAULT(nextval('ca_seq')),
    symbol      VARCHAR NOT NULL,
    action_type VARCHAR NOT NULL,
    action_date DATE NOT NULL,
    recorded_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    details     VARCHAR NOT NULL
);
"""


class CorporateActionLog:
    """Append-only event log for corporate actions (splits, dividends).

    Rows are **never** updated or deleted -- this is an event-sourced log.

    Args:
        db_path: Path to the DuckDB database file.  Use ``Path(":memory:")``
                 for an ephemeral in-memory database (useful for tests).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(db_path))
        self._conn.execute("CREATE SEQUENCE IF NOT EXISTS ca_seq START 1")
        self._conn.execute(_CA_DDL)
        logger.info("CorporateActionLog initialized: %s", db_path)

    # ── Write ────────────────────────────────────────────────────────────────

    def record_action(
        self,
        symbol: str,
        action_type: str,
        action_date: date,
        details: dict,
    ) -> Diagnostics:
        """Append a corporate action event.

        Args:
            symbol: Stock ticker.
            action_type: One of "SPLIT", "DIVIDEND", etc.
            action_date: Effective date of the action.
            details: Arbitrary metadata (e.g. split ratio, dividend amount).
        """
        diag = Diagnostics()

        if action_type not in ("SPLIT", "DIVIDEND", "MERGER", "SPINOFF"):
            diag.warning(
                _SRC,
                f"Non-standard action_type '{action_type}' for {symbol}",
            )

        try:
            self._conn.execute(
                """
                INSERT INTO corporate_actions (symbol, action_type, action_date, details)
                VALUES ($1, $2, $3::DATE, $4)
                """,
                [symbol, action_type, str(action_date), json.dumps(details)],
            )
            diag.info(_SRC, f"Recorded {action_type} for {symbol} on {action_date}")
        except Exception as exc:
            diag.error(_SRC, f"Corporate action write failed: {exc}")

        return diag

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_actions_since(self, since: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Return all corporate actions with action_date >= since."""
        diag = Diagnostics()
        empty = pd.DataFrame(columns=["id", "symbol", "action_type", "action_date", "recorded_at", "details"])

        try:
            result = self._conn.execute(
                """
                SELECT id, symbol, action_type, action_date, recorded_at, details
                FROM corporate_actions
                WHERE action_date >= $1::DATE
                ORDER BY action_date, symbol
                """,
                [str(since)],
            ).fetchdf()
            diag.info(_SRC, f"Found {len(result)} actions since {since}")
            return result, diag
        except Exception as exc:
            diag.error(_SRC, f"Read failed: {exc}")
            return empty, diag

    def get_actions_for_symbol(self, symbol: str) -> tuple[pd.DataFrame, Diagnostics]:
        """Return all corporate actions for a single symbol."""
        diag = Diagnostics()
        empty = pd.DataFrame(columns=["id", "symbol", "action_type", "action_date", "recorded_at", "details"])

        try:
            result = self._conn.execute(
                """
                SELECT id, symbol, action_type, action_date, recorded_at, details
                FROM corporate_actions
                WHERE symbol = $1
                ORDER BY action_date
                """,
                [symbol],
            ).fetchdf()
            diag.info(_SRC, f"Found {len(result)} actions for {symbol}")
            return result, diag
        except Exception as exc:
            diag.error(_SRC, f"Read failed: {exc}")
            return empty, diag

    def get_pending_actions(
        self,
        held_symbols: list[str],
        since: date,
    ) -> tuple[pd.DataFrame, Diagnostics]:
        """Return corporate actions since ``since`` that affect held positions.

        This is the key query for the execution engine: "what corporate actions
        have happened recently for stocks I currently hold?"
        """
        diag = Diagnostics()
        empty = pd.DataFrame(columns=["id", "symbol", "action_type", "action_date", "recorded_at", "details"])

        if not held_symbols:
            diag.warning(_SRC, "Empty held_symbols list — returning empty DataFrame")
            return empty, diag

        try:
            result = self._conn.execute(
                """
                SELECT id, symbol, action_type, action_date, recorded_at, details
                FROM corporate_actions
                WHERE symbol IN (SELECT UNNEST($1::VARCHAR[]))
                  AND action_date >= $2::DATE
                ORDER BY action_date, symbol
                """,
                [held_symbols, str(since)],
            ).fetchdf()
            diag.info(
                _SRC,
                f"Found {len(result)} pending actions for {len(held_symbols)} held symbols",
            )
            return result, diag
        except Exception as exc:
            diag.error(_SRC, f"Read failed: {exc}")
            return empty, diag

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.info("CorporateActionLog closed: %s", self._db_path)

    def __enter__(self) -> CorporateActionLog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
