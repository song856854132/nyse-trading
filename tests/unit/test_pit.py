"""Tests for nyse_core.pit — Point-in-Time enforcement."""

from datetime import date

import numpy as np
import pandas as pd

from nyse_core.contracts import DiagLevel
from nyse_core.pit import enforce_pit_lags


class TestFutureRejection:
    """Features must never leak future data."""

    def test_future_dated_features_are_nand(self) -> None:
        """A feature filed tomorrow must be NaN when as_of_date is today."""
        df = pd.DataFrame(
            {
                "date": [date(2022, 6, 10), date(2022, 6, 11)],
                "revenue": [100.0, 200.0],
            }
        )
        result, diag = enforce_pit_lags(
            df,
            publication_lags={"revenue": 0},
            as_of_date=date(2022, 6, 10),
            max_age_days=30,
        )
        assert result.loc[0, "revenue"] == 100.0
        assert np.isnan(result.loc[1, "revenue"])

    def test_publication_lag_blocks_recent_filing(self) -> None:
        """FINRA short interest with 11-day pub lag filed June 1 is NOT available June 10."""
        df = pd.DataFrame(
            {
                "date": [date(2022, 6, 1)],
                "short_interest": [5_000_000.0],
            }
        )
        result, diag = enforce_pit_lags(
            df,
            publication_lags={"short_interest": 11},
            as_of_date=date(2022, 6, 10),
            max_age_days=60,
        )
        # Filed June 1 + 11 days = June 12 publication. June 10 < June 12 → NaN.
        assert np.isnan(result.loc[0, "short_interest"])

    def test_publication_lag_allows_old_enough_filing(self) -> None:
        """FINRA short interest filed June 1 IS available on June 12 (11d lag)."""
        df = pd.DataFrame(
            {
                "date": [date(2022, 6, 1)],
                "short_interest": [5_000_000.0],
            }
        )
        result, diag = enforce_pit_lags(
            df,
            publication_lags={"short_interest": 11},
            as_of_date=date(2022, 6, 12),
            max_age_days=60,
        )
        assert result.loc[0, "short_interest"] == 5_000_000.0


class TestMaxAgeBoundary:
    """Stale data must be NaN'd."""

    def test_stale_feature_nand(self) -> None:
        """Feature older than max_age_days is NaN'd."""
        df = pd.DataFrame(
            {
                "date": [date(2022, 1, 1)],
                "eps": [3.50],
            }
        )
        result, diag = enforce_pit_lags(
            df,
            publication_lags={},
            as_of_date=date(2022, 7, 1),
            max_age_days=90,
        )
        # Age = 182 days > 90 → NaN
        assert np.isnan(result.loc[0, "eps"])

    def test_within_max_age_is_kept(self) -> None:
        """Feature within max_age_days is kept."""
        df = pd.DataFrame(
            {
                "date": [date(2022, 6, 1)],
                "eps": [3.50],
            }
        )
        result, diag = enforce_pit_lags(
            df,
            publication_lags={},
            as_of_date=date(2022, 6, 15),
            max_age_days=90,
        )
        assert result.loc[0, "eps"] == 3.50

    def test_exact_boundary_is_kept(self) -> None:
        """Feature exactly max_age_days old is still valid (not stale)."""
        # June 1 + 90 days = Aug 30, 2024
        df = pd.DataFrame(
            {
                "date": [date(2022, 6, 1)],
                "eps": [3.50],
            }
        )
        result, _ = enforce_pit_lags(
            df,
            publication_lags={},
            as_of_date=date(2022, 8, 30),
            max_age_days=90,
        )
        assert result.loc[0, "eps"] == 3.50


class TestDiagnostics:
    """Diagnostics must log enforcement actions."""

    def test_diag_reports_nan_counts(self) -> None:
        df = pd.DataFrame(
            {
                "date": [date(2022, 1, 1), date(2022, 6, 1)],
                "feat_a": [10.0, 20.0],
            }
        )
        _, diag = enforce_pit_lags(
            df,
            publication_lags={},
            as_of_date=date(2022, 6, 15),
            max_age_days=90,
        )
        warnings = [m for m in diag.messages if m.level == DiagLevel.WARNING]
        assert len(warnings) >= 1
        assert "stale" in warnings[0].message.lower() or "nan" in warnings[0].message.lower()

    def test_missing_date_column_produces_error(self) -> None:
        df = pd.DataFrame({"feat_a": [1.0, 2.0]})
        _, diag = enforce_pit_lags(df, {}, date(2022, 6, 1), 90)
        assert diag.has_errors
