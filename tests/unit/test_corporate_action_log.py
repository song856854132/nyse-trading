"""Unit tests for nyse_ats.storage.corporate_action_log."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from nyse_ats.storage.corporate_action_log import CorporateActionLog

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def log(tmp_path: Path) -> CorporateActionLog:
    """Create a CorporateActionLog backed by a temporary DuckDB file."""
    db_path = tmp_path / "corp_actions.duckdb"
    cal = CorporateActionLog(db_path)
    yield cal
    cal.close()


class TestRecordAction:
    """Tests for record_action."""

    def test_record_split(self, log: CorporateActionLog) -> None:
        """Recording a stock split should succeed without errors."""
        diag = log.record_action("AAPL", "SPLIT", date(2024, 6, 15), {"ratio": "4:1"})
        assert not diag.has_errors

    def test_record_dividend(self, log: CorporateActionLog) -> None:
        """Recording a dividend should succeed without errors."""
        diag = log.record_action("MSFT", "DIVIDEND", date(2024, 3, 14), {"amount": 0.75})
        assert not diag.has_errors

    def test_non_standard_action_type_warns(self, log: CorporateActionLog) -> None:
        """A non-standard action_type should produce a warning, not an error."""
        diag = log.record_action("XYZ", "BUYBACK", date(2024, 6, 1), {"price": 50.0})
        assert not diag.has_errors
        assert diag.has_warnings

    def test_multiple_actions_same_symbol(self, log: CorporateActionLog) -> None:
        """Multiple actions for the same symbol can be stored (append-only)."""
        for i in range(3):
            diag = log.record_action(
                symbol="AAPL",
                action_type="DIVIDEND",
                action_date=date(2024, 3 * (i + 1), 15),
                details={"amount": 0.75 + i * 0.05},
            )
            assert not diag.has_errors

        df, diag2 = log.get_actions_for_symbol("AAPL")
        assert not diag2.has_errors
        assert len(df) == 3


class TestGetActionsSince:
    """Tests for get_actions_since date filtering."""

    def test_filters_by_date(self, log: CorporateActionLog) -> None:
        """Only actions on or after the given date should be returned."""
        log.record_action("AAPL", "SPLIT", date(2024, 1, 10), {"ratio": "2:1"})
        log.record_action("MSFT", "DIVIDEND", date(2024, 3, 15), {"amount": 0.5})
        log.record_action("GOOG", "SPLIT", date(2024, 6, 20), {"ratio": "20:1"})

        df, diag = log.get_actions_since(date(2024, 3, 1))
        assert not diag.has_errors
        assert len(df) == 2  # MSFT dividend + GOOG split
        symbols = set(df["symbol"].tolist())
        assert "AAPL" not in symbols

    def test_no_match_returns_empty(self, log: CorporateActionLog) -> None:
        """If no actions exist after the given date, an empty DataFrame is returned."""
        log.record_action("AAPL", "SPLIT", date(2024, 1, 10), {"ratio": "2:1"})

        df, diag = log.get_actions_since(date(2025, 1, 1))
        assert not diag.has_errors
        assert df.empty

    def test_empty_log_returns_empty(self, log: CorporateActionLog) -> None:
        """Empty log returns empty DataFrame with correct columns."""
        df, diag = log.get_actions_since(date(2024, 1, 1))
        assert not diag.has_errors
        assert len(df) == 0
        assert "symbol" in df.columns


class TestGetActionsForSymbol:
    """Tests for get_actions_for_symbol."""

    def test_returns_only_matching_symbol(self, log: CorporateActionLog) -> None:
        """Only actions for the requested symbol should be returned."""
        log.record_action("AAPL", "SPLIT", date(2024, 1, 10), {"ratio": "4:1"})
        log.record_action("MSFT", "DIVIDEND", date(2024, 3, 15), {"amount": 0.5})
        log.record_action("AAPL", "DIVIDEND", date(2024, 6, 15), {"amount": 0.22})

        df, diag = log.get_actions_for_symbol("AAPL")
        assert not diag.has_errors
        assert len(df) == 2
        assert (df["symbol"] == "AAPL").all()

    def test_nonexistent_symbol_returns_empty(self, log: CorporateActionLog) -> None:
        """Querying a symbol with no actions returns an empty DataFrame."""
        df, diag = log.get_actions_for_symbol("ZZZ")
        assert not diag.has_errors
        assert df.empty


class TestGetPendingActions:
    """Tests for get_pending_actions (held symbols intersection)."""

    def test_filters_by_held_symbols_and_date(self, log: CorporateActionLog) -> None:
        """Only actions for held symbols since the given date are returned."""
        log.record_action("AAPL", "SPLIT", date(2024, 1, 10), {"ratio": "4:1"})
        log.record_action("MSFT", "DIVIDEND", date(2024, 3, 15), {"amount": 0.5})
        log.record_action("GOOG", "SPLIT", date(2024, 6, 20), {"ratio": "20:1"})
        log.record_action("AAPL", "DIVIDEND", date(2024, 7, 1), {"amount": 0.22})

        df, diag = log.get_pending_actions(
            held_symbols=["AAPL", "GOOG"],
            since=date(2024, 3, 1),
        )
        assert not diag.has_errors
        assert len(df) == 2  # GOOG split + AAPL dividend (not AAPL split before cutoff)
        assert set(df["symbol"].tolist()) == {"AAPL", "GOOG"}

    def test_empty_held_symbols_returns_empty_with_warning(self, log: CorporateActionLog) -> None:
        """Empty held_symbols list returns an empty DataFrame with a warning."""
        log.record_action("AAPL", "SPLIT", date(2024, 6, 15), {"ratio": "4:1"})

        df, diag = log.get_pending_actions(held_symbols=[], since=date(2024, 1, 1))
        assert df.empty
        assert diag.has_warnings


class TestAppendOnlyGuarantee:
    """Tests verifying the event-sourced append-only property."""

    def test_no_update_or_delete_methods(self, log: CorporateActionLog) -> None:
        """CorporateActionLog has no update or delete methods."""
        public_methods = [m for m in dir(log) if not m.startswith("_")]
        for method_name in public_methods:
            assert "update" not in method_name.lower()
            assert "delete" not in method_name.lower()
            assert "remove" not in method_name.lower()

    def test_ids_are_strictly_increasing(self, log: CorporateActionLog) -> None:
        """Each appended event should get a strictly increasing id."""
        for i in range(5):
            log.record_action(
                symbol="AAPL",
                action_type="DIVIDEND",
                action_date=date(2024, 1, 1 + i),
                details={"seq": i},
            )

        df, diag = log.get_actions_for_symbol("AAPL")
        assert not diag.has_errors
        ids = df["id"].tolist()
        assert ids == sorted(ids)
        assert len(set(ids)) == 5  # all unique

    def test_duplicate_events_are_separate_rows(self, log: CorporateActionLog) -> None:
        """Logging the same action twice creates two separate rows."""
        log.record_action("AAPL", "SPLIT", date(2024, 6, 15), {"ratio": "4:1"})
        log.record_action("AAPL", "SPLIT", date(2024, 6, 15), {"ratio": "4:1"})

        df, diag = log.get_actions_for_symbol("AAPL")
        assert not diag.has_errors
        assert len(df) == 2  # Two separate events, not one
