"""Property tests for sell buffer turnover reduction.

CONTRACT:
- With sell_buffer > 1.0, turnover is <= turnover without buffer
  (the buffer retains existing holdings longer, reducing churn)
"""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nyse_core.allocator import select_top_n

# ── Strategies ───────────────────────────────────────────────────────────────


@st.composite
def _scored_universe_with_holdings(
    draw: st.DrawFn,
) -> tuple[pd.Series, set[str], int]:
    """Generate a scored universe where some stocks are currently held.

    Returns (scores: pd.Series, current_holdings: set[str], top_n: int).
    """
    n_stocks = draw(st.integers(min_value=15, max_value=80))
    symbols = [f"SYM_{i:02d}" for i in range(n_stocks)]
    scores = [draw(st.floats(min_value=-2.0, max_value=2.0)) for _ in range(n_stocks)]
    series = pd.Series(scores, index=symbols)

    top_n = draw(st.integers(min_value=5, max_value=min(30, n_stocks - 1)))

    # Current holdings: pick a subset of stocks (some in top_n, some not)
    n_held = draw(st.integers(min_value=3, max_value=min(top_n + 5, n_stocks)))
    held_indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=n_stocks - 1),
            min_size=n_held,
            max_size=n_held,
            unique=True,
        ),
    )
    current_holdings = {symbols[i] for i in held_indices}

    return series, current_holdings, top_n


# ── Property: buffer reduces turnover ────────────────────────────────────────


class TestSellBufferReducesTurnover:
    """With sell_buffer > 1.0, turnover is <= turnover without buffer."""

    @pytest.mark.property
    @given(universe=_scored_universe_with_holdings())
    @settings(max_examples=200, deadline=None)
    def test_sell_buffer_reduces_turnover(
        self,
        universe: tuple[pd.Series, set[str], int],
    ) -> None:
        """Turnover with sell_buffer=1.5 must be <= turnover with sell_buffer=1.0."""
        scores, current_holdings, top_n = universe

        # Selection WITHOUT buffer (buffer=1.0 means no buffer)
        selected_no_buffer, _ = select_top_n(
            scores,
            n=top_n,
            current_holdings=current_holdings,
            sell_buffer=1.0,
        )

        # Selection WITH buffer
        selected_with_buffer, _ = select_top_n(
            scores,
            n=top_n,
            current_holdings=current_holdings,
            sell_buffer=1.5,
        )

        # Turnover = number of position changes
        set_no_buf = set(selected_no_buffer)
        set_with_buf = set(selected_with_buffer)

        turnover_no_buffer = len(current_holdings - set_no_buf) + len(set_no_buf - current_holdings)
        turnover_with_buffer = len(current_holdings - set_with_buf) + len(set_with_buf - current_holdings)

        assert turnover_with_buffer <= turnover_no_buffer, (
            f"Buffer turnover {turnover_with_buffer} > no-buffer turnover {turnover_no_buffer}. "
            f"Holdings={current_holdings}, no_buf={set_no_buf}, with_buf={set_with_buf}"
        )

    @pytest.mark.property
    @given(universe=_scored_universe_with_holdings())
    @settings(max_examples=200, deadline=None)
    def test_buffer_retains_more_holdings(
        self,
        universe: tuple[pd.Series, set[str], int],
    ) -> None:
        """With buffer, the number of retained holdings should be >= without buffer."""
        scores, current_holdings, top_n = universe

        selected_no_buffer, _ = select_top_n(
            scores,
            n=top_n,
            current_holdings=current_holdings,
            sell_buffer=1.0,
        )
        selected_with_buffer, _ = select_top_n(
            scores,
            n=top_n,
            current_holdings=current_holdings,
            sell_buffer=1.5,
        )

        retained_no_buffer = len(current_holdings & set(selected_no_buffer))
        retained_with_buffer = len(current_holdings & set(selected_with_buffer))

        assert retained_with_buffer >= retained_no_buffer, (
            f"Buffer retained {retained_with_buffer} < no-buffer retained {retained_no_buffer}"
        )
