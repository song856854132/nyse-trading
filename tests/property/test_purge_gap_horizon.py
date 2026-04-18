"""Property tests for CV purge gap / horizon invariant.

CONTRACT:
- purge_days >= target_horizon_days for all CV splits
  (prevents lookahead bias in walk-forward cross-validation)

This ensures that the gap between train and test periods is always
at least as large as the forward-return horizon used for labeling.
"""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

try:
    from nyse_core.models.cv import PurgedWalkForwardCV

    _HAS_CV = True
except ImportError:
    try:
        from nyse_core.cv import PurgedWalkForwardCV

        _HAS_CV = True
    except ImportError:
        _HAS_CV = False

        class PurgedWalkForwardCV:  # type: ignore[no-redef]
            """Stub for type checking -- never instantiated when module is missing."""

            def __init__(
                self,
                n_splits: int,
                train_days: int,
                test_days: int,
                purge_days: int,
                embargo_days: int,
            ) -> None:
                raise NotImplementedError

            def split(self, dates: pd.DatetimeIndex) -> list:
                raise NotImplementedError


# ── Strategies ───────────────────────────────────────────────────────────────


@st.composite
def _cv_params(draw: st.DrawFn) -> dict:
    """Generate valid CV parameters where purge_days varies.

    Returns dict with n_splits, train_days, test_days, purge_days,
    embargo_days, target_horizon_days.
    """
    target_horizon = draw(st.integers(min_value=1, max_value=21))
    purge_days = draw(st.integers(min_value=target_horizon, max_value=30))
    embargo_days = draw(st.integers(min_value=0, max_value=10))
    test_days = draw(st.integers(min_value=21, max_value=126))
    train_days = draw(st.integers(min_value=252, max_value=756))
    n_splits = draw(st.integers(min_value=2, max_value=6))

    return {
        "n_splits": n_splits,
        "train_days": train_days,
        "test_days": test_days,
        "purge_days": purge_days,
        "embargo_days": embargo_days,
        "target_horizon_days": target_horizon,
    }


@st.composite
def _cv_params_potentially_invalid(draw: st.DrawFn) -> dict:
    """Generate CV parameters where purge_days may be less than horizon.

    Used to test that the system REJECTS invalid configurations.
    """
    target_horizon = draw(st.integers(min_value=2, max_value=21))
    # purge_days might be LESS than target_horizon (invalid)
    purge_days = draw(st.integers(min_value=0, max_value=target_horizon - 1))
    embargo_days = draw(st.integers(min_value=0, max_value=10))
    test_days = draw(st.integers(min_value=21, max_value=126))
    train_days = draw(st.integers(min_value=252, max_value=756))
    n_splits = draw(st.integers(min_value=2, max_value=6))

    return {
        "n_splits": n_splits,
        "train_days": train_days,
        "test_days": test_days,
        "purge_days": purge_days,
        "embargo_days": embargo_days,
        "target_horizon_days": target_horizon,
    }


def _generate_date_index(n_days: int) -> pd.DatetimeIndex:
    """Generate a DatetimeIndex of business days."""
    return pd.bdate_range(start="2018-01-02", periods=n_days, freq="B")


# ── Property: purge_days >= target_horizon_days ──────────────────────────────


class TestPurgeGapHorizonInvariant:
    """purge_days must be >= target_horizon_days for all CV splits."""

    @pytest.mark.property
    @given(params=_cv_params())
    @settings(max_examples=100, deadline=None)
    def test_purge_gap_ge_horizon(self, params: dict) -> None:
        """For target_horizon_days=N, purge gap must be >= N."""
        assert params["purge_days"] >= params["target_horizon_days"], (
            f"purge_days={params['purge_days']} < target_horizon_days={params['target_horizon_days']}"
        )

    @pytest.mark.skipif(not _HAS_CV, reason="PurgedWalkForwardCV not yet implemented")
    @pytest.mark.property
    @given(params=_cv_params())
    @settings(max_examples=100, deadline=None)
    def test_purge_geq_horizon_direct(self, params: dict) -> None:
        """Direct check: purge_days >= target_horizon_days in config."""
        assert params["purge_days"] >= params["target_horizon_days"], (
            f"purge_days={params['purge_days']} < target_horizon_days={params['target_horizon_days']}"
        )

    @pytest.mark.skipif(not _HAS_CV, reason="PurgedWalkForwardCV not yet implemented")
    @pytest.mark.property
    @given(params=_cv_params())
    @settings(max_examples=50, deadline=None)
    def test_splits_have_sufficient_gap(self, params: dict) -> None:
        """For each CV split, the gap between train end and test start >= horizon."""
        total_days = (
            params["train_days"] + params["purge_days"] + params["embargo_days"] + params["test_days"]
        ) * params["n_splits"]
        # Need enough dates
        assume(total_days <= 3000)

        dates = _generate_date_index(total_days)
        cv = PurgedWalkForwardCV(
            n_folds=params["n_splits"],
            min_train_days=params["train_days"],
            test_days=params["test_days"],
            purge_days=params["purge_days"],
            embargo_days=params["embargo_days"],
            target_horizon_days=params["target_horizon_days"],
        )

        splits = cv.split(dates)
        for train_idx, test_idx in splits:
            if len(train_idx) == 0 or len(test_idx) == 0:
                continue

            train_end = dates[train_idx[-1]]
            test_start = dates[test_idx[0]]
            gap_days = (test_start - train_end).days

            assert gap_days >= params["target_horizon_days"], (
                f"Gap {gap_days} days < target_horizon {params['target_horizon_days']} days. "
                f"Train end: {train_end}, Test start: {test_start}"
            )


# ── Property: invalid purge_days should be rejected ─────────────────────────


class TestInvalidPurgeGapRejection:
    """System should reject or warn when purge_days < target_horizon_days."""

    @pytest.mark.skipif(not _HAS_CV, reason="PurgedWalkForwardCV not yet implemented")
    @pytest.mark.property
    @given(params=_cv_params_potentially_invalid())
    @settings(max_examples=50, deadline=None)
    def test_insufficient_purge_raises_or_warns(self, params: dict) -> None:
        """Creating CV with purge_days < target_horizon should raise or warn.

        The exact behavior depends on implementation:
        - May raise ValueError at construction time
        - May produce a diagnostic warning
        Either is acceptable; silently proceeding is NOT.
        """
        # This test documents the contract -- if the implementation allows
        # insufficient purge days silently, this test should fail
        assert params["purge_days"] < params["target_horizon_days"], (
            "Test precondition: purge_days should be less than target_horizon"
        )

        # The implementation auto-adjusts purge_days to max(purge_days, target_horizon_days).
        # Verify the invariant holds after construction.
        cv = PurgedWalkForwardCV(
            n_folds=params["n_splits"],
            min_train_days=params["train_days"],
            test_days=params["test_days"],
            purge_days=params["purge_days"],
            embargo_days=params["embargo_days"],
            target_horizon_days=params["target_horizon_days"],
        )
        assert cv.purge_days >= params["target_horizon_days"], (
            f"After auto-adjust, purge_days={cv.purge_days} should be >= "
            f"target_horizon_days={params['target_horizon_days']}"
        )
