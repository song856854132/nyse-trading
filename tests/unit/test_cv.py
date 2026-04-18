"""Unit tests for PurgedWalkForwardCV."""

from __future__ import annotations

import warnings

import pandas as pd
import pytest

from nyse_core.cv import PurgedWalkForwardCV

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_dates(n_days: int, start: str = "2015-01-02") -> pd.DatetimeIndex:
    """Create a business-day DatetimeIndex with *n_days* entries."""
    return pd.bdate_range(start=start, periods=n_days)


# ── Purge auto-adjust ────────────────────────────────────────────────────────


class TestPurgeAutoAdjust:
    def test_purge_at_least_target_horizon(self):
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=504,
            test_days=126,
            purge_days=3,
            embargo_days=5,
            target_horizon_days=10,
        )
        assert cv.purge_days == 10, "purge should auto-adjust to target_horizon_days"

    def test_purge_unchanged_when_already_larger(self):
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=504,
            test_days=126,
            purge_days=20,
            embargo_days=5,
            target_horizon_days=5,
        )
        assert cv.purge_days == 20, "purge should stay at 20 when > target_horizon"


# ── Minimum 2-year training ─────────────────────────────────────────────────


class TestMinTrainYears:
    def test_min_train_enforced(self):
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=100,  # deliberately small
            test_days=63,
            purge_days=5,
            embargo_days=5,
        )
        # min_train_days should be bumped to 2 * 252 = 504
        assert cv.min_train_days == 504

    def test_min_train_respected_when_larger(self):
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=600,
            test_days=63,
            purge_days=5,
            embargo_days=5,
        )
        assert cv.min_train_days == 600


# ── Expanding window ────────────────────────────────────────────────────────


class TestExpandingWindow:
    def test_train_windows_expand(self):
        """Train end index should grow across folds (expanding, not rolling)."""
        n_days = 2000
        dates = _make_dates(n_days)
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        folds = list(cv.split(dates))
        assert len(folds) >= 2, "Should produce at least 2 folds"

        train_ends = [train_idx[-1] for train_idx, _ in folds]
        for i in range(1, len(train_ends)):
            assert train_ends[i] > train_ends[i - 1], (
                f"Fold {i} train end ({train_ends[i]}) must be > fold {i - 1} train end ({train_ends[i - 1]})"
            )

    def test_train_always_starts_at_zero(self):
        """All folds should start training from index 0."""
        dates = _make_dates(2000)
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        for train_idx, _ in cv.split(dates):
            assert train_idx[0] == 0, "Expanding window must start at index 0"


# ── Purge and embargo gaps ──────────────────────────────────────────────────


class TestPurgeEmbargoGaps:
    def test_no_overlap_train_test(self):
        """Train and test indices must not overlap."""
        dates = _make_dates(2000)
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        for train_idx, test_idx in cv.split(dates):
            overlap = set(train_idx) & set(test_idx)
            assert len(overlap) == 0, f"Train/test overlap: {overlap}"

    def test_purge_gap_exists(self):
        """There must be a gap of at least purge_days between train end and test start."""
        dates = _make_dates(2000)
        purge = 10
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=504,
            test_days=126,
            purge_days=purge,
            embargo_days=5,
        )
        for train_idx, test_idx in cv.split(dates):
            gap = test_idx[0] - train_idx[-1] - 1
            assert gap >= purge, f"Gap {gap} < purge {purge}"


# ── Not enough data ─────────────────────────────────────────────────────────


class TestInsufficientData:
    def test_raises_on_too_few_observations(self):
        dates = _make_dates(100)
        cv = PurgedWalkForwardCV(
            n_folds=5,
            min_train_days=504,
            test_days=126,
            purge_days=5,
            embargo_days=5,
        )
        with pytest.raises(ValueError, match="Not enough data"):
            list(cv.split(dates))


# ── max_params_check (AP-7) ─────────────────────────────────────────────────


class TestMaxParamsCheck:
    def test_passes_when_sufficient_obs(self):
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=63,
            purge_days=5,
            embargo_days=5,
        )
        # 60 monthly obs = 5 years * 12 months, ~1260 trading days
        result, diag = cv.max_params_check(n_params=6, n_obs=1260)
        assert result is True
        assert not diag.has_errors

    def test_warns_too_many_params(self):
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=63,
            purge_days=5,
            embargo_days=5,
        )
        # 30 monthly obs = ~630 trading days, with 6 params -> should warn
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result, diag = cv.max_params_check(n_params=6, n_obs=630)
            assert result is False
            assert diag.has_warnings
            assert len(w) == 1
            assert "AP-7" in str(w[0].message)

    def test_passes_few_params(self):
        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=504,
            test_days=63,
            purge_days=5,
            embargo_days=5,
        )
        # 5 params is <= MAX_PARAMS_WARNING, should always pass
        result, _ = cv.max_params_check(n_params=5, n_obs=100)
        assert result is True


# ── Validation ───────────────────────────────────────────────────────────────


class TestValidation:
    def test_invalid_n_folds(self):
        with pytest.raises(ValueError):
            PurgedWalkForwardCV(
                n_folds=0,
                min_train_days=504,
                test_days=63,
                purge_days=5,
                embargo_days=5,
            )

    def test_invalid_test_days(self):
        with pytest.raises(ValueError):
            PurgedWalkForwardCV(
                n_folds=2,
                min_train_days=504,
                test_days=0,
                purge_days=5,
                embargo_days=5,
            )
