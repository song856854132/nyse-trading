"""Tests for nyse_core.universe — S&P 500 historical reconstitution."""

from datetime import date

import pandas as pd

from nyse_core.contracts import DiagLevel
from nyse_core.universe import get_universe_at_date


def _make_changes(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    """Helper: create constituency_changes DataFrame from (date, symbol, action) tuples."""
    return pd.DataFrame(rows, columns=["date", "symbol", "action"])


class TestReconstitution:
    """Core reconstitution logic."""

    def test_initial_members_returned_with_no_changes(self) -> None:
        changes = _make_changes([])
        members, diag = get_universe_at_date(
            changes, target_date=date(2022, 6, 1), initial_members=["AAPL", "MSFT"]
        )
        assert members == ["AAPL", "MSFT"]

    def test_add_applies(self) -> None:
        changes = _make_changes([("2022-03-01", "GOOG", "ADD")])
        members, _ = get_universe_at_date(changes, target_date=date(2022, 6, 1), initial_members=["AAPL"])
        assert "GOOG" in members
        assert "AAPL" in members

    def test_remove_applies(self) -> None:
        changes = _make_changes([("2022-03-01", "AAPL", "REMOVE")])
        members, _ = get_universe_at_date(
            changes, target_date=date(2022, 6, 1), initial_members=["AAPL", "MSFT"]
        )
        assert "AAPL" not in members
        assert "MSFT" in members

    def test_add_then_remove(self) -> None:
        changes = _make_changes(
            [
                ("2022-01-01", "TSLA", "ADD"),
                ("2022-04-01", "TSLA", "REMOVE"),
            ]
        )
        members, _ = get_universe_at_date(changes, target_date=date(2022, 6, 1), initial_members=["AAPL"])
        assert "TSLA" not in members

    def test_output_is_sorted(self) -> None:
        changes = _make_changes([])
        members, _ = get_universe_at_date(
            changes, target_date=date(2022, 6, 1), initial_members=["MSFT", "AAPL", "GOOG"]
        )
        assert members == sorted(members)


class TestPointInTime:
    """Future constituency changes must never be used."""

    def test_future_add_excluded(self) -> None:
        changes = _make_changes([("2023-01-01", "NVDA", "ADD")])
        members, diag = get_universe_at_date(changes, target_date=date(2022, 6, 1), initial_members=["AAPL"])
        assert "NVDA" not in members
        info_msgs = [m for m in diag.messages if m.level == DiagLevel.INFO]
        assert any("future" in m.message.lower() for m in info_msgs)

    def test_future_remove_excluded(self) -> None:
        changes = _make_changes([("2023-01-01", "AAPL", "REMOVE")])
        members, _ = get_universe_at_date(changes, target_date=date(2022, 6, 1), initial_members=["AAPL"])
        assert "AAPL" in members

    def test_exact_date_change_included(self) -> None:
        """A change on the target_date itself IS applied."""
        changes = _make_changes([("2022-06-01", "NVDA", "ADD")])
        members, _ = get_universe_at_date(changes, target_date=date(2022, 6, 1), initial_members=["AAPL"])
        assert "NVDA" in members


class TestDiagnostics:
    """Diagnostics must report adds/removes."""

    def test_diag_reports_counts(self) -> None:
        changes = _make_changes(
            [
                ("2022-01-01", "GOOG", "ADD"),
                ("2022-02-01", "AAPL", "REMOVE"),
            ]
        )
        _, diag = get_universe_at_date(
            changes, target_date=date(2022, 6, 1), initial_members=["AAPL", "MSFT"]
        )
        info_msgs = [m for m in diag.messages if m.level == DiagLevel.INFO]
        assert any("1" in m.message and "add" in m.message.lower() for m in info_msgs)

    def test_missing_columns_produces_error(self) -> None:
        bad_df = pd.DataFrame({"foo": [1]})
        _, diag = get_universe_at_date(bad_df, date(2022, 6, 1), ["AAPL"])
        assert diag.has_errors
