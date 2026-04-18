"""Purged Walk-Forward Cross-Validation with expanding windows.

Implements time-series CV that prevents lookahead bias through purge and embargo
zones between train and test sets.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import numpy as np

from nyse_core.contracts import Diagnostics
from nyse_core.schema import (
    MAX_PARAMS_WARNING,
    MIN_TRAIN_YEARS,
    TRADING_DAYS_PER_YEAR,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pandas as pd


class PurgedWalkForwardCV:
    """Expanding-window walk-forward CV with purge and embargo gaps.

    Train windows expand from the earliest date, ensuring a minimum of
    ``min_train_days`` (default 2 years). Purge zone between train and test
    is auto-adjusted to be at least ``target_horizon_days`` to avoid leaking
    the prediction target into training data.

    Parameters
    ----------
    n_folds : int
        Number of out-of-sample test folds.
    min_train_days : int
        Minimum number of trading days in the first training window.
    test_days : int
        Number of trading days per test fold.
    purge_days : int
        Number of trading days to drop between train end and test start.
    embargo_days : int
        Number of trading days to drop after test end before the next fold
        can use that data for training.
    target_horizon_days : int
        Forward-return horizon. Purge is auto-adjusted to
        ``max(purge_days, target_horizon_days)``.
    """

    def __init__(
        self,
        n_folds: int,
        min_train_days: int,
        test_days: int,
        purge_days: int,
        embargo_days: int,
        target_horizon_days: int = 5,
    ) -> None:
        if n_folds < 1:
            raise ValueError("n_folds must be >= 1")
        if min_train_days < 1:
            raise ValueError("min_train_days must be >= 1")
        if test_days < 1:
            raise ValueError("test_days must be >= 1")

        self.n_folds = n_folds
        self.min_train_days = max(min_train_days, MIN_TRAIN_YEARS * TRADING_DAYS_PER_YEAR)
        self.test_days = test_days
        # AP purge auto-adjust: purge >= target horizon
        self.purge_days = max(purge_days, target_horizon_days)
        self.embargo_days = embargo_days
        self.target_horizon_days = target_horizon_days

    def split(self, dates: pd.DatetimeIndex) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """Generate (train_indices, test_indices) for each fold.

        Uses an EXPANDING train window. The first fold starts training from
        index 0 through at least ``min_train_days`` observations. Subsequent
        folds keep the same start but extend the training end.

        Parameters
        ----------
        dates : pd.DatetimeIndex
            Sorted datetime index representing observation dates.

        Yields
        ------
        tuple[np.ndarray, np.ndarray]
            Integer index arrays for (train, test) observations.
        """
        n = len(dates)
        gap = self.purge_days + self.embargo_days

        # Total days required: min_train + n_folds * (test + gap) - last embargo
        total_needed = self.min_train_days + self.n_folds * (self.test_days + gap) - self.embargo_days
        if n < total_needed:
            raise ValueError(
                f"Not enough data: need {total_needed} observations, got {n}. Reduce n_folds or test_days."
            )

        # Lay out test folds from the END of the series working backwards
        # so that each fold uses a distinct test window and train is expanding.
        folds: list[tuple[int, int]] = []
        test_end = n
        for _ in range(self.n_folds):
            test_start = test_end - self.test_days
            folds.append((test_start, test_end))
            test_end = test_start - gap
        folds.reverse()

        for test_start, test_end_idx in folds:
            train_end = test_start - self.purge_days
            if train_end < self.min_train_days:
                # Skip folds where we don't have enough training data
                continue
            train_indices = np.arange(0, train_end)
            test_indices = np.arange(test_start, test_end_idx)
            yield train_indices, test_indices

    def max_params_check(self, n_params: int, n_obs: int) -> tuple[bool, Diagnostics]:
        """Check AP-7: warn if n_params > 5 with < 60 monthly observations.

        Parameters
        ----------
        n_params : int
            Number of model parameters / features.
        n_obs : int
            Number of observations (trading days) in the training set.

        Returns
        -------
        tuple[bool, Diagnostics]
            (True if check passes, diagnostics).
        """
        diag = Diagnostics()
        source = "cv.max_params_check"
        monthly_obs = n_obs / (TRADING_DAYS_PER_YEAR / 12)
        if n_params > MAX_PARAMS_WARNING and monthly_obs < 60:
            warnings.warn(
                f"AP-7: {n_params} parameters with only {monthly_obs:.0f} monthly "
                f"observations (< 60). Risk of overfitting.",
                UserWarning,
                stacklevel=2,
            )
            diag.warning(
                source,
                f"AP-7: {n_params} parameters with only {monthly_obs:.0f} monthly "
                f"observations (< 60). Risk of overfitting.",
                n_params=n_params,
                monthly_obs=monthly_obs,
            )
            return False, diag
        diag.info(source, "max_params_check passed", n_params=n_params, monthly_obs=monthly_obs)
        return True, diag


class ExecutionPurgedCV(PurgedWalkForwardCV):
    """Walk-forward CV with additional execution delay purge.

    Extends PurgedWalkForwardCV to account for the T+1 execution delay:
    signals generated on Friday are executed Monday. The purge gap is
    increased by ``execution_delay_days`` to prevent label leakage
    through the execution window.

    Parameters
    ----------
    execution_delay_days : int
        Days between signal generation and trade execution (default 1).
        Added to the purge gap on top of target_horizon_days.
    """

    def __init__(
        self,
        n_folds: int,
        min_train_days: int,
        test_days: int,
        purge_days: int,
        embargo_days: int,
        target_horizon_days: int = 5,
        execution_delay_days: int = 1,
    ) -> None:
        self.execution_delay_days = execution_delay_days
        # Add execution delay to purge to prevent leakage through the
        # signal-to-execution window
        super().__init__(
            n_folds=n_folds,
            min_train_days=min_train_days,
            test_days=test_days,
            purge_days=purge_days + execution_delay_days,
            embargo_days=embargo_days,
            target_horizon_days=target_horizon_days,
        )
