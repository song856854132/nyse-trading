"""Property tests for position cap invariants.

CONTRACT:
- After apply_position_caps, no single weight exceeds max_pct (10% default)
- Weights still sum to <= 1.0
- All weights remain non-negative

Uses risk.apply_position_caps (the actual module location).
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from nyse_core.risk import apply_position_caps
from nyse_core.schema import MAX_POSITION_PCT

# ── Strategies ───────────────────────────────────────────────────────────────


# Generate a dict of symbol -> weight where weights sum to ~1.0
@st.composite
def _weight_dict(draw: st.DrawFn) -> dict[str, float]:
    """Generate a weight dict that sums to 1.0 with 3-50 positions."""
    n = draw(st.integers(min_value=3, max_value=50))
    raw = [draw(st.floats(min_value=0.001, max_value=1.0)) for _ in range(n)]
    total = sum(raw)
    normalized = [w / total for w in raw]
    symbols = [f"SYM_{i:02d}" for i in range(n)]
    return dict(zip(symbols, normalized, strict=False))


_max_pct_strategy = st.floats(min_value=0.02, max_value=0.25)


# ── Property: no weight exceeds max_pct ──────────────────────────────────────


class TestPositionCapEnforcement:
    """After apply_position_caps, no individual weight exceeds max_pct."""

    @pytest.mark.property
    @given(weights=_weight_dict(), max_pct=_max_pct_strategy)
    @settings(max_examples=200, deadline=None)
    def test_no_weight_exceeds_cap(
        self,
        weights: dict[str, float],
        max_pct: float,
    ) -> None:
        """Every weight in the result must be <= max_pct."""
        result, _diag = apply_position_caps(weights, max_pct)

        for sym, w in result.items():
            assert w <= max_pct + 1e-10, f"{sym} weight {w:.6f} exceeds cap {max_pct:.4f}"

    @pytest.mark.property
    @given(weights=_weight_dict(), max_pct=_max_pct_strategy)
    @settings(max_examples=200, deadline=None)
    def test_no_negative_weights(
        self,
        weights: dict[str, float],
        max_pct: float,
    ) -> None:
        """All weights must remain non-negative after capping."""
        result, _diag = apply_position_caps(weights, max_pct)

        for sym, w in result.items():
            assert w >= 0.0, f"{sym} weight {w:.6f} is negative"

    @pytest.mark.property
    @given(weights=_weight_dict())
    @settings(max_examples=100, deadline=None)
    def test_no_stock_exceeds_10_pct(self, weights: dict[str, float]) -> None:
        """With default MAX_POSITION_PCT=0.10, no stock should exceed 10%."""
        result, _diag = apply_position_caps(weights, max_pct=MAX_POSITION_PCT)

        for sym, w in result.items():
            assert w <= MAX_POSITION_PCT + 1e-10, f"{sym} weight {w:.6f} exceeds 10% cap"


# ── Property: weights still sum to <= 1.0 ───────────────────────────────────


class TestPositionCapSumInvariant:
    """After apply_position_caps, weights still sum to approximately 1.0."""

    @pytest.mark.property
    @given(weights=_weight_dict(), max_pct=_max_pct_strategy)
    @settings(max_examples=200, deadline=None)
    def test_weights_sum_to_target(
        self,
        weights: dict[str, float],
        max_pct: float,
    ) -> None:
        """Sum of all weights should be <= 1.0 after capping."""
        result, _diag = apply_position_caps(weights, max_pct)
        total = sum(result.values())

        assert total <= 1.0 + 1e-6, f"Weights sum to {total:.8f}, expected <= 1.0"

    @pytest.mark.property
    @given(weights=_weight_dict(), max_pct=_max_pct_strategy)
    @settings(max_examples=200, deadline=None)
    def test_weights_sum_preserves_when_feasible(
        self,
        weights: dict[str, float],
        max_pct: float,
    ) -> None:
        """Sum of all weights should be ~1.0 after redistribution when feasible."""
        # Only valid if max_pct comfortably fits all positions
        n = len(weights)
        assume(max_pct * n >= 1.0 + 0.05)  # need room for redistribution

        result, _diag = apply_position_caps(weights, max_pct)
        total = sum(result.values())

        np.testing.assert_allclose(
            total,
            1.0,
            atol=1e-6,
            err_msg=f"Weights sum to {total:.8f}, expected ~1.0",
        )
