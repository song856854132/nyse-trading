"""Unit tests for nyse_core.corporate_actions."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from nyse_core.corporate_actions import adjust_for_splits, detect_pending_actions

# ── adjust_for_splits ────────────────────────────────────────────────────────


class TestAdjustForSplits:
    """Tests for historical price/volume split adjustment."""

    @pytest.fixture()
    def price_data(self) -> pd.DataFrame:
        """Simple price history for AAPL around a split date."""
        return pd.DataFrame(
            {
                "date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),  # split date
                    date(2024, 1, 4),
                    date(2024, 1, 5),
                ],
                "symbol": ["AAPL"] * 5,
                "close": [400.0, 420.0, 100.0, 105.0, 110.0],
                "volume": [1_000_000, 1_100_000, 4_500_000, 4_000_000, 4_200_000],
            }
        )

    def test_4_to_1_split_adjusts_pre_split_prices(self, price_data: pd.DataFrame) -> None:
        """Pre-split prices should be divided by 4."""
        splits = pd.DataFrame(
            {
                "date": [date(2024, 1, 3)],
                "symbol": ["AAPL"],
                "ratio": [4.0],
            }
        )
        adjusted, diag = adjust_for_splits(price_data, splits)

        # Pre-split rows (dates before 2024-01-03)
        pre = adjusted[adjusted["date"] < date(2024, 1, 3)]
        assert pre.iloc[0]["close"] == pytest.approx(100.0)  # 400 / 4
        assert pre.iloc[1]["close"] == pytest.approx(105.0)  # 420 / 4
        assert not diag.has_errors

    def test_4_to_1_split_adjusts_pre_split_volume(self, price_data: pd.DataFrame) -> None:
        """Pre-split volumes should be multiplied by 4."""
        splits = pd.DataFrame(
            {
                "date": [date(2024, 1, 3)],
                "symbol": ["AAPL"],
                "ratio": [4.0],
            }
        )
        adjusted, _ = adjust_for_splits(price_data, splits)

        pre = adjusted[adjusted["date"] < date(2024, 1, 3)]
        assert pre.iloc[0]["volume"] == pytest.approx(4_000_000)  # 1M * 4
        assert pre.iloc[1]["volume"] == pytest.approx(4_400_000)  # 1.1M * 4

    def test_post_split_prices_unchanged(self, price_data: pd.DataFrame) -> None:
        """Post-split prices should remain unchanged."""
        splits = pd.DataFrame(
            {
                "date": [date(2024, 1, 3)],
                "symbol": ["AAPL"],
                "ratio": [4.0],
            }
        )
        adjusted, _ = adjust_for_splits(price_data, splits)

        post = adjusted[adjusted["date"] >= date(2024, 1, 3)]
        orig_post = price_data[price_data["date"] >= date(2024, 1, 3)]
        assert list(post["close"]) == list(orig_post["close"])

    def test_no_splits_returns_copy(self, price_data: pd.DataFrame) -> None:
        """Empty splits DataFrame should return an unmodified copy."""
        empty_splits = pd.DataFrame(columns=["date", "symbol", "ratio"])
        adjusted, diag = adjust_for_splits(price_data, empty_splits)
        pd.testing.assert_frame_equal(adjusted, price_data)

    def test_invalid_ratio_produces_error(self, price_data: pd.DataFrame) -> None:
        """Zero or negative ratio should produce an error diagnostic."""
        splits = pd.DataFrame(
            {
                "date": [date(2024, 1, 3)],
                "symbol": ["AAPL"],
                "ratio": [0.0],
            }
        )
        _, diag = adjust_for_splits(price_data, splits)
        assert diag.has_errors

    def test_original_not_mutated(self, price_data: pd.DataFrame) -> None:
        """Original DataFrame should not be modified."""
        original_close = price_data["close"].copy()
        splits = pd.DataFrame(
            {
                "date": [date(2024, 1, 3)],
                "symbol": ["AAPL"],
                "ratio": [4.0],
            }
        )
        adjust_for_splits(price_data, splits)
        pd.testing.assert_series_equal(price_data["close"], original_close)

    def test_multiple_symbols(self) -> None:
        """Splits for different symbols should only affect the right one."""
        prices = pd.DataFrame(
            {
                "date": [date(2024, 1, 1), date(2024, 1, 2)] * 2,
                "symbol": ["AAPL", "AAPL", "MSFT", "MSFT"],
                "close": [400.0, 100.0, 300.0, 310.0],
                "volume": [1_000_000, 4_000_000, 500_000, 520_000],
            }
        )
        splits = pd.DataFrame(
            {
                "date": [date(2024, 1, 2)],
                "symbol": ["AAPL"],
                "ratio": [4.0],
            }
        )
        adjusted, _ = adjust_for_splits(prices, splits)
        # AAPL pre-split adjusted, MSFT untouched
        msft = adjusted[adjusted["symbol"] == "MSFT"]
        assert list(msft["close"]) == [300.0, 310.0]


# ── detect_pending_actions ───────────────────────────────────────────────────


class TestDetectPendingActions:
    """Tests for detecting upcoming corporate actions."""

    def test_detects_upcoming_action(self) -> None:
        """A held stock with an action after 'since' should be detected."""
        actions = pd.DataFrame(
            {
                "date": [date(2024, 6, 15)],
                "symbol": ["AAPL"],
                "action_type": ["dividend"],
            }
        )
        result, diag = detect_pending_actions(
            held_symbols=["AAPL"],
            actions=actions,
            since=date(2024, 6, 1),
        )
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"
        assert diag.has_warnings

    def test_ignores_non_held_symbols(self) -> None:
        """Actions for non-held stocks should be ignored."""
        actions = pd.DataFrame(
            {
                "date": [date(2024, 6, 15)],
                "symbol": ["GOOG"],
                "action_type": ["split"],
            }
        )
        result, _ = detect_pending_actions(
            held_symbols=["AAPL"],
            actions=actions,
            since=date(2024, 6, 1),
        )
        assert len(result) == 0

    def test_ignores_actions_before_since(self) -> None:
        """Actions before 'since' date should be excluded."""
        actions = pd.DataFrame(
            {
                "date": [date(2024, 5, 1)],
                "symbol": ["AAPL"],
                "action_type": ["dividend"],
            }
        )
        result, _ = detect_pending_actions(
            held_symbols=["AAPL"],
            actions=actions,
            since=date(2024, 6, 1),
        )
        assert len(result) == 0

    def test_empty_actions_returns_empty(self) -> None:
        """Empty actions DataFrame should return empty list."""
        empty = pd.DataFrame(columns=["date", "symbol", "action_type"])
        result, diag = detect_pending_actions(
            held_symbols=["AAPL"],
            actions=empty,
            since=date(2024, 6, 1),
        )
        assert result == []
        assert not diag.has_warnings

    def test_multiple_actions_for_same_stock(self) -> None:
        """Multiple pending actions for the same stock should all be returned."""
        actions = pd.DataFrame(
            {
                "date": [date(2024, 6, 10), date(2024, 6, 20)],
                "symbol": ["AAPL", "AAPL"],
                "action_type": ["dividend", "split"],
            }
        )
        result, _ = detect_pending_actions(
            held_symbols=["AAPL"],
            actions=actions,
            since=date(2024, 6, 1),
        )
        assert len(result) == 2
