"""Tests for nyse_core.impute — cross-sectional NaN imputation."""

import numpy as np
import pandas as pd

from nyse_core.contracts import DiagLevel
from nyse_core.impute import cross_sectional_impute


class TestMedianImputation:
    """Features with <30% missing should be imputed with cross-sectional median."""

    def test_single_nan_imputed_with_median(self) -> None:
        """One NaN out of 5 stocks (20% missing) gets median-filled."""
        df = pd.DataFrame(
            {
                "date": ["2024-06-01"] * 5,
                "feat_a": [10.0, 20.0, np.nan, 40.0, 50.0],
            }
        )
        result, diag = cross_sectional_impute(df, max_missing_pct=0.30)
        # Median of [10, 20, 40, 50] = 30.0
        assert result.loc[2, "feat_a"] == 30.0

    def test_no_nans_unchanged(self) -> None:
        df = pd.DataFrame(
            {
                "date": ["2024-06-01"] * 3,
                "feat_a": [1.0, 2.0, 3.0],
            }
        )
        result, _ = cross_sectional_impute(df)
        pd.testing.assert_frame_equal(result, df)


class TestDropHighMissing:
    """Features with >=30% missing should be dropped (set to NaN) for that date."""

    def test_high_missing_dropped(self) -> None:
        """2 NaN out of 4 stocks = 50% → entire column NaN'd for that date."""
        df = pd.DataFrame(
            {
                "date": ["2024-06-01"] * 4,
                "feat_a": [10.0, np.nan, np.nan, 40.0],
            }
        )
        result, diag = cross_sectional_impute(df, max_missing_pct=0.30)
        # 50% missing ≥ 30% → all NaN for that date
        assert result["feat_a"].isna().all()
        assert diag.has_warnings

    def test_exact_threshold_dropped(self) -> None:
        """Exactly 30% missing → DROP (>= threshold)."""
        # 3 out of 10 = 30%
        vals = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, np.nan, np.nan, np.nan]
        df = pd.DataFrame(
            {
                "date": ["2024-06-01"] * 10,
                "feat_a": vals,
            }
        )
        result, _ = cross_sectional_impute(df, max_missing_pct=0.30)
        assert result["feat_a"].isna().all()

    def test_just_below_threshold_imputed(self) -> None:
        """29% missing → impute (below 30% threshold)."""
        # 2 out of 7 ≈ 28.6%
        vals = [10.0, 20.0, 30.0, 40.0, 50.0, np.nan, np.nan]
        df = pd.DataFrame(
            {
                "date": ["2024-06-01"] * 7,
                "feat_a": vals,
            }
        )
        result, _ = cross_sectional_impute(df, max_missing_pct=0.30)
        assert not result["feat_a"].isna().any()

    def test_per_date_independence(self) -> None:
        """Different dates are handled independently."""
        df = pd.DataFrame(
            {
                "date": ["2024-06-01"] * 4 + ["2024-06-02"] * 4,
                "feat_a": [
                    10.0,
                    np.nan,
                    np.nan,
                    40.0,  # date 1: 50% missing → drop
                    10.0,
                    20.0,
                    30.0,
                    np.nan,  # date 2: 25% missing → impute
                ],
            }
        )
        result, _ = cross_sectional_impute(df, max_missing_pct=0.30)
        # Date 1 rows (0-3): all NaN
        assert result.loc[0:3, "feat_a"].isna().all()
        # Date 2 rows (4-7): imputed, no NaN
        assert not result.loc[4:7, "feat_a"].isna().any()


class TestAllNanDropped:
    """Features with 100% NaN should be entirely dropped (set to NaN)."""

    def test_all_nan_dropped(self) -> None:
        """100% NaN feature should remain all-NaN (dropped)."""
        df = pd.DataFrame(
            {
                "date": ["2024-06-01"] * 5,
                "feat_a": [np.nan, np.nan, np.nan, np.nan, np.nan],
            }
        )
        result, diag = cross_sectional_impute(df, max_missing_pct=0.30)
        # 100% missing >= 30% -> all NaN for that date
        assert result["feat_a"].isna().all()
        assert diag.has_warnings


class TestDiagnostics:
    """Diagnostics must log imputation counts and dropped features."""

    def test_imputation_count_logged(self) -> None:
        df = pd.DataFrame(
            {
                "date": ["2024-06-01"] * 5,
                "feat_a": [10.0, 20.0, np.nan, 40.0, 50.0],
            }
        )
        _, diag = cross_sectional_impute(df)
        info_msgs = [m for m in diag.messages if m.level == DiagLevel.INFO]
        assert any("1" in m.message and "imput" in m.message.lower() for m in info_msgs)

    def test_dropped_feature_warned(self) -> None:
        df = pd.DataFrame(
            {
                "date": ["2024-06-01"] * 4,
                "feat_a": [10.0, np.nan, np.nan, 40.0],
            }
        )
        _, diag = cross_sectional_impute(df)
        warnings = [m for m in diag.messages if m.level == DiagLevel.WARNING]
        assert len(warnings) >= 1
        assert "feat_a" in warnings[0].message

    def test_missing_date_column_produces_error(self) -> None:
        df = pd.DataFrame({"feat_a": [1.0, 2.0]})
        _, diag = cross_sectional_impute(df)
        assert diag.has_errors
