"""Unit tests for nyse_core.allocator."""

from __future__ import annotations

import pandas as pd
import pytest

from nyse_core.allocator import equal_weight, select_top_n

# ── select_top_n ─────────────────────────────────────────────────────────────


class TestSelectTopN:
    """Tests for top-N selection with sell buffer."""

    @pytest.fixture()
    def scores(self) -> pd.Series:
        """10 stocks scored 10 down to 1."""
        return pd.Series(
            {f"S{i:02d}": float(10 - i) for i in range(10)},
        )

    def test_basic_top_5(self, scores: pd.Series) -> None:
        """Without holdings, pick top 5 by score."""
        selected, diag = select_top_n(scores, n=5)
        assert len(selected) == 5
        assert selected[0] == "S00"  # highest score
        assert not diag.has_errors

    def test_sell_buffer_retains_holdings(self, scores: pd.Series) -> None:
        """Existing holdings within buffer should be retained."""
        # S05 is rank 6 — within buffer (5 * 1.5 = 7.5)
        selected, _ = select_top_n(scores, n=5, current_holdings={"S05"}, sell_buffer=1.5)
        assert "S05" in selected
        assert len(selected) == 5

    def test_sell_buffer_drops_far_out_holdings(self, scores: pd.Series) -> None:
        """Existing holdings below buffer threshold should be dropped."""
        # S09 is rank 10 — outside buffer (5 * 1.5 = 7.5)
        selected, _ = select_top_n(scores, n=5, current_holdings={"S09"}, sell_buffer=1.5)
        assert "S09" not in selected

    def test_sell_buffer_reduces_turnover(self, scores: pd.Series) -> None:
        """With sell buffer, a borderline holding survives that wouldn't
        survive without a buffer."""
        # S06 is rank 7 — would not be in top 5 pure selection
        pure, _ = select_top_n(scores, n=5)
        buffered, _ = select_top_n(scores, n=5, current_holdings={"S06"}, sell_buffer=1.5)
        assert "S06" not in pure
        assert "S06" in buffered

    def test_ties_prefer_held_stocks(self) -> None:
        """When two stocks have the same score at the cutoff, prefer the held one."""
        scores = pd.Series({"A": 5.0, "B": 5.0, "C": 3.0})
        selected, _ = select_top_n(scores, n=1, current_holdings={"B"}, sell_buffer=1.5)
        assert "B" in selected

    def test_ties_alphabetical_when_no_holdings(self) -> None:
        """Tied stocks with no holding preference should be alphabetical."""
        scores = pd.Series({"C": 5.0, "A": 5.0, "B": 5.0})
        selected, _ = select_top_n(scores, n=2)
        # All tied at score 5.0 — alphabetical A, B selected
        assert selected == ["A", "B"]

    def test_top_n_exceeds_universe(self) -> None:
        """Requesting more than available should select all + warn."""
        scores = pd.Series({"A": 3.0, "B": 2.0, "C": 1.0})
        selected, diag = select_top_n(scores, n=10)
        assert len(selected) == 3
        assert diag.has_warnings

    def test_empty_scores(self) -> None:
        """Empty scores should return empty list + warning."""
        selected, diag = select_top_n(pd.Series(dtype=float), n=5)
        assert selected == []
        assert diag.has_warnings

    def test_all_nan_scores(self) -> None:
        """All-NaN scores should return empty list + warning."""
        scores = pd.Series({"A": float("nan"), "B": float("nan"), "C": float("nan")})
        selected, diag = select_top_n(scores, n=2)
        assert selected == []
        assert diag.has_warnings


# ── equal_weight ─────────────────────────────────────────────────────────────


class TestEqualWeight:
    """Tests for equal-weight allocation."""

    def test_basic(self) -> None:
        """N stocks should each get 1/N."""
        weights, diag = equal_weight(["A", "B", "C", "D"])
        assert len(weights) == 4
        assert all(w == pytest.approx(0.25) for w in weights.values())
        assert not diag.has_errors

    def test_single_stock(self) -> None:
        """Single stock gets 100%."""
        weights, _ = equal_weight(["A"])
        assert weights["A"] == pytest.approx(1.0)

    def test_empty_list(self) -> None:
        """Empty selection should return empty dict + warning."""
        weights, diag = equal_weight([])
        assert weights == {}
        assert diag.has_warnings

    def test_weights_sum_to_one(self) -> None:
        """Weights for any selection should sum to 1.0."""
        syms = [f"S{i}" for i in range(20)]
        weights, _ = equal_weight(syms)
        assert sum(weights.values()) == pytest.approx(1.0)
