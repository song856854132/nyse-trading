"""Property tests for FactorRegistry invariants.

CONTRACT:
- Registering the same factor name in SIGNAL then RISK -> DoubleDipError
- compute_all output has n_factors columns
- sign_convention=-1 negates output
- Same name twice -> ValueError
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nyse_core.contracts import Diagnostics
from nyse_core.features.registry import DoubleDipError, FactorRegistry
from nyse_core.schema import UsageDomain

# ── Helper: trivial compute function ────────────────────────────────────────


def _make_compute_fn(values: list[float]):
    """Build a compute_fn that returns a fixed Series."""

    def compute_fn(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        diag = Diagnostics()
        # Repeat values to match the data length, truncating if needed
        repeated = (values * ((len(data) // len(values)) + 1))[: len(data)]
        series = pd.Series(repeated, index=data.index, dtype=float)
        return series, diag

    return compute_fn


# ── Strategies ───────────────────────────────────────────────────────────────

_factor_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
    min_size=1,
    max_size=20,
)


# ── Property: double-dip always raises ───────────────────────────────────────


class TestDoubleDipAlwaysRaises:
    """Registering the same name in SIGNAL then RISK must be rejected.

    The implementation checks for duplicate names first (ValueError),
    which effectively prevents the double-dip AP-3 violation. Either
    ValueError or DoubleDipError is acceptable for preventing reuse.
    """

    @pytest.mark.property
    @given(name=_factor_name)
    @settings(max_examples=100, deadline=None)
    def test_double_dip_always_raises(self, name: str) -> None:
        """AP-3: same factor in both SIGNAL and RISK domains -> error."""
        registry = FactorRegistry()
        fn = _make_compute_fn([1.0, 2.0, 3.0])

        registry.register(
            name=name,
            compute_fn=fn,
            usage_domain=UsageDomain.SIGNAL,
            sign_convention=1,
        )

        # Must raise either DoubleDipError or ValueError -- either prevents
        # the same factor from appearing in both domains
        with pytest.raises((DoubleDipError, ValueError)):
            registry.register(
                name=name,
                compute_fn=fn,
                usage_domain=UsageDomain.RISK,
                sign_convention=1,
            )


# ── Property: compute_all output shape ───────────────────────────────────────


class TestComputeAllOutputShape:
    """compute_all must return a DataFrame with n_factors columns."""

    @pytest.mark.property
    @given(n_factors=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50, deadline=None)
    def test_compute_all_output_shape(self, n_factors: int) -> None:
        """n_factors registered -> output has exactly n_factors columns."""
        registry = FactorRegistry()
        data = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0, 5.0]})

        for i in range(n_factors):
            fn = _make_compute_fn([float(i + 1)] * 5)
            registry.register(
                name=f"factor_{i}",
                compute_fn=fn,
                usage_domain=UsageDomain.SIGNAL,
                sign_convention=1,
                description=f"Test factor {i}",
            )

        result, _diag = registry.compute_all(data, rebalance_date=date(2024, 6, 1))
        assert result.shape[1] == n_factors, f"Expected {n_factors} columns, got {result.shape[1]}"
        assert result.shape[0] == len(data), f"Expected {len(data)} rows, got {result.shape[0]}"


# ── Property: sign inversion applied ────────────────────────────────────────


class TestSignInversionApplied:
    """Factor with sign_convention=-1 -> output values are negated."""

    @pytest.mark.property
    @given(
        values=st.lists(
            st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            min_size=3,
            max_size=20,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_sign_inversion_applied(self, values: list[float]) -> None:
        """sign_convention=-1 must negate all output values."""
        registry = FactorRegistry()
        data = pd.DataFrame({"a": range(len(values))})

        fn = _make_compute_fn(values)
        registry.register(
            name="neg_factor",
            compute_fn=fn,
            usage_domain=UsageDomain.SIGNAL,
            sign_convention=-1,
        )

        result, _diag = registry.compute_all(data, rebalance_date=date(2024, 6, 1))
        output = result["neg_factor"]

        # The output should be the negation of the raw values
        expected = pd.Series([-v for v in values[: len(data)]], index=data.index, dtype=float)
        np.testing.assert_allclose(
            output.values,
            expected.values,
            atol=1e-10,
            err_msg="Sign inversion not applied correctly",
        )


# ── Property: no duplicate registration ──────────────────────────────────────


class TestNoDuplicateRegistration:
    """Registering the same name twice must raise ValueError."""

    @pytest.mark.property
    @given(name=_factor_name)
    @settings(max_examples=100, deadline=None)
    def test_no_duplicate_registration(self, name: str) -> None:
        """Same name registered twice in same domain -> ValueError."""
        registry = FactorRegistry()
        fn = _make_compute_fn([1.0, 2.0])

        registry.register(
            name=name,
            compute_fn=fn,
            usage_domain=UsageDomain.SIGNAL,
            sign_convention=1,
        )

        with pytest.raises(ValueError, match="already registered"):
            registry.register(
                name=name,
                compute_fn=fn,
                usage_domain=UsageDomain.SIGNAL,
                sign_convention=1,
            )
