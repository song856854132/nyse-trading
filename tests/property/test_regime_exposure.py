"""Property tests for regime-dependent exposure invariants.

CONTRACT:
- In BEAR regime, total exposure <= bear_exposure (0.4)
- In BULL regime, total exposure == bull_exposure (1.0)

The implementation module may not exist yet. Tests define the expected
interface and will skip gracefully if the module is not available.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nyse_core.schema import BEAR_EXPOSURE, BULL_EXPOSURE, RegimeState

try:
    from nyse_core.allocator import apply_regime_scaling

    _HAS_REGIME_SCALING = True
except ImportError:
    _HAS_REGIME_SCALING = False

    def apply_regime_scaling(
        weights: dict[str, float],
        regime: RegimeState,
        bull_exposure: float = BULL_EXPOSURE,
        bear_exposure: float = BEAR_EXPOSURE,
    ) -> tuple[dict[str, float], object]:
        """Stub."""
        raise NotImplementedError


# ── Strategies ───────────────────────────────────────────────────────────────


@st.composite
def _weight_dict(draw: st.DrawFn) -> dict[str, float]:
    """Generate a weight dict that sums to 1.0."""
    n = draw(st.integers(min_value=3, max_value=30))
    raw = [draw(st.floats(min_value=0.001, max_value=1.0)) for _ in range(n)]
    total = sum(raw)
    normalized = [w / total for w in raw]
    symbols = [f"SYM_{i:02d}" for i in range(n)]
    return dict(zip(symbols, normalized, strict=False))


# ── Property: BEAR regime caps exposure ──────────────────────────────────────


class TestBearRegimeExposure:
    """In BEAR regime, total exposure must be <= bear_exposure (0.4)."""

    @pytest.mark.skipif(
        not _HAS_REGIME_SCALING,
        reason="apply_regime_scaling not yet implemented",
    )
    @given(weights=_weight_dict())
    @settings(max_examples=200, deadline=None)
    def test_bear_exposure_capped(self, weights: dict[str, float]) -> None:
        """Total weight in BEAR regime must not exceed BEAR_EXPOSURE."""
        result, _diag = apply_regime_scaling(
            weights,
            RegimeState.BEAR,
            bull_exposure=BULL_EXPOSURE,
            bear_exposure=BEAR_EXPOSURE,
        )

        total = sum(result.values())
        assert total <= BEAR_EXPOSURE + 1e-6, f"BEAR exposure {total:.6f} exceeds limit {BEAR_EXPOSURE}"

    @pytest.mark.skipif(
        not _HAS_REGIME_SCALING,
        reason="apply_regime_scaling not yet implemented",
    )
    @given(weights=_weight_dict())
    @settings(max_examples=200, deadline=None)
    def test_bear_weights_non_negative(self, weights: dict[str, float]) -> None:
        """All weights must remain non-negative in BEAR regime."""
        result, _diag = apply_regime_scaling(
            weights,
            RegimeState.BEAR,
            bull_exposure=BULL_EXPOSURE,
            bear_exposure=BEAR_EXPOSURE,
        )

        for sym, w in result.items():
            assert w >= 0.0, f"{sym} weight {w:.6f} is negative in BEAR regime"

    @pytest.mark.skipif(
        not _HAS_REGIME_SCALING,
        reason="apply_regime_scaling not yet implemented",
    )
    @given(weights=_weight_dict())
    @settings(max_examples=200, deadline=None)
    def test_bear_preserves_relative_weights(self, weights: dict[str, float]) -> None:
        """Relative proportions should be maintained in BEAR scaling."""
        result, _diag = apply_regime_scaling(
            weights,
            RegimeState.BEAR,
            bull_exposure=BULL_EXPOSURE,
            bear_exposure=BEAR_EXPOSURE,
        )

        # All weights should be scaled by the same factor
        if len(result) >= 2:
            syms = list(result.keys())
            for i in range(1, len(syms)):
                if weights[syms[0]] > 1e-10 and weights[syms[i]] > 1e-10:
                    ratio_input = weights[syms[0]] / weights[syms[i]]
                    ratio_output = result[syms[0]] / result[syms[i]]
                    np.testing.assert_allclose(
                        ratio_input,
                        ratio_output,
                        rtol=1e-6,
                        err_msg="Relative weights changed during BEAR scaling",
                    )


# ── Property: BULL regime maintains full exposure ────────────────────────────


class TestBullRegimeExposure:
    """In BULL regime, total exposure should equal bull_exposure (1.0)."""

    @pytest.mark.skipif(
        not _HAS_REGIME_SCALING,
        reason="apply_regime_scaling not yet implemented",
    )
    @given(weights=_weight_dict())
    @settings(max_examples=200, deadline=None)
    def test_bull_exposure_equals_target(self, weights: dict[str, float]) -> None:
        """Total weight in BULL regime must be ~BULL_EXPOSURE (1.0)."""
        result, _diag = apply_regime_scaling(
            weights,
            RegimeState.BULL,
            bull_exposure=BULL_EXPOSURE,
            bear_exposure=BEAR_EXPOSURE,
        )

        total = sum(result.values())
        np.testing.assert_allclose(
            total,
            BULL_EXPOSURE,
            atol=1e-6,
            err_msg=f"BULL exposure {total:.6f} != {BULL_EXPOSURE}",
        )

    @pytest.mark.skipif(
        not _HAS_REGIME_SCALING,
        reason="apply_regime_scaling not yet implemented",
    )
    @given(weights=_weight_dict())
    @settings(max_examples=200, deadline=None)
    def test_bull_weights_non_negative(self, weights: dict[str, float]) -> None:
        """All weights must remain non-negative in BULL regime."""
        result, _diag = apply_regime_scaling(
            weights,
            RegimeState.BULL,
            bull_exposure=BULL_EXPOSURE,
            bear_exposure=BEAR_EXPOSURE,
        )

        for sym, w in result.items():
            assert w >= 0.0, f"{sym} weight {w:.6f} is negative in BULL regime"
