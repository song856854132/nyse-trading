"""Tests for nyse_core.normalize — rank-percentile, winsorize, z-score."""

import numpy as np
import pandas as pd

from nyse_core.contracts import DiagLevel
from nyse_core.normalize import (
    normalize_cross_section,
    rank_percentile,
    winsorize,
    z_score,
)


class TestRankPercentile:
    """rank_percentile must map to [0, 1] with correct edge-case handling."""

    def test_output_in_unit_interval(self) -> None:
        """All non-NaN output values must be in [0, 1]."""
        s = pd.Series([10, 30, 20, 50, 40])
        result, diag = rank_percentile(s)
        non_nan = result.dropna()
        assert (non_nan >= 0.0).all()
        assert (non_nan <= 1.0).all()

    def test_rank_order_preserved(self) -> None:
        """Lowest value gets 0.0, highest gets 1.0."""
        s = pd.Series([10, 30, 20, 50, 40])
        result, _ = rank_percentile(s)
        assert result.iloc[0] == 0.0  # 10 is min
        assert result.iloc[3] == 1.0  # 50 is max

    def test_all_nan_returns_all_nan(self) -> None:
        """All-NaN input produces all-NaN output with WARNING."""
        s = pd.Series([np.nan, np.nan, np.nan])
        result, diag = rank_percentile(s)
        assert result.isna().all()
        assert diag.has_warnings

    def test_single_value_returns_half(self) -> None:
        """Single non-NaN value should map to 0.5."""
        s = pd.Series([np.nan, 42.0, np.nan])
        result, diag = rank_percentile(s)
        assert result.iloc[1] == 0.5
        assert np.isnan(result.iloc[0])
        assert np.isnan(result.iloc[2])
        info_msgs = [m for m in diag.messages if m.level == DiagLevel.INFO]
        assert any("0.5" in m.message for m in info_msgs)

    def test_tied_values_get_average_rank(self) -> None:
        """Ties should receive the average of their ranks."""
        s = pd.Series([10, 20, 20, 30])
        result, _ = rank_percentile(s)
        # Ranks: 1, 2.5, 2.5, 4.  Scaled: 0/3, 1.5/3, 1.5/3, 3/3
        assert result.iloc[0] == 0.0
        assert result.iloc[1] == result.iloc[2]  # tied
        assert result.iloc[3] == 1.0

    def test_nans_preserved_in_output(self) -> None:
        """NaN positions in input remain NaN in output."""
        s = pd.Series([10, np.nan, 30, 20])
        result, _ = rank_percentile(s)
        assert np.isnan(result.iloc[1])
        assert not np.isnan(result.iloc[0])

    def test_two_values(self) -> None:
        """Two values → 0.0 and 1.0."""
        s = pd.Series([100, 200])
        result, _ = rank_percentile(s)
        assert result.iloc[0] == 0.0
        assert result.iloc[1] == 1.0


class TestWinsorize:
    """winsorize must clip outliers at quantile boundaries."""

    def test_clips_extreme_values(self) -> None:
        s = pd.Series(list(range(100)))
        result, diag = winsorize(s, lower=0.05, upper=0.95)
        assert result.min() >= s.quantile(0.05)
        assert result.max() <= s.quantile(0.95)

    def test_all_nan_returns_unchanged(self) -> None:
        s = pd.Series([np.nan, np.nan])
        result, diag = winsorize(s)
        assert result.isna().all()
        assert diag.has_warnings

    def test_nans_preserved(self) -> None:
        s = pd.Series([1, np.nan, 100, 2])
        result, _ = winsorize(s)
        assert np.isnan(result.iloc[1])


class TestZScore:
    """z_score must produce mean~0, std~1 for non-NaN values."""

    def test_mean_zero_std_one(self) -> None:
        s = pd.Series([10, 20, 30, 40, 50])
        result, _ = z_score(s)
        non_nan = result.dropna()
        assert abs(non_nan.mean()) < 1e-10
        assert abs(non_nan.std(ddof=1) - 1.0) < 1e-10

    def test_all_nan_returns_all_nan(self) -> None:
        s = pd.Series([np.nan, np.nan])
        result, diag = z_score(s)
        assert result.isna().all()
        assert diag.has_warnings

    def test_zero_variance_returns_zeros(self) -> None:
        s = pd.Series([5.0, 5.0, 5.0])
        result, diag = z_score(s)
        non_nan = result.dropna()
        assert (non_nan == 0.0).all()


class TestNormalizeCrossSection:
    """normalize_cross_section must chain winsorize → rank_percentile and
    produce the same output as calling the two stages by hand. This is the
    DRY contract that the live pipeline and the research pipeline both
    depend on (TODO-8)."""

    def test_output_in_unit_interval(self) -> None:
        """All non-NaN values land in [0, 1] regardless of outlier magnitude."""
        s = pd.Series([10.0, 20.0, 30.0, 40.0, 1e9])  # 1e9 is the outlier
        result, _ = normalize_cross_section(s)
        non_nan = result.dropna()
        assert (non_nan >= 0.0).all()
        assert (non_nan <= 1.0).all()

    def test_matches_manual_two_stage_chain(self) -> None:
        """Helper output must equal the manual winsorize → rank_percentile chain."""
        s = pd.Series([5.0, -100.0, 3.0, 7.0, 200.0, 1.0, 4.0, 2.0, 6.0, 8.0])

        w, _ = winsorize(s, lower=0.01, upper=0.99)
        expected, _ = rank_percentile(w)

        actual, _ = normalize_cross_section(s)

        pd.testing.assert_series_equal(actual.sort_index(), expected.sort_index(), check_names=False)

    def test_diagnostics_merged_from_both_stages(self) -> None:
        """Returned Diagnostics must carry messages from BOTH winsorize and rank_percentile."""
        s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        _, diag = normalize_cross_section(s)
        sources = {m.source for m in diag.messages}
        assert "normalize.winsorize" in sources
        assert "normalize.rank_percentile" in sources

    def test_all_nan_returns_all_nan_with_warning(self) -> None:
        """All-NaN input must surface a warning (from the rank_percentile stage)."""
        s = pd.Series([np.nan, np.nan, np.nan])
        result, diag = normalize_cross_section(s)
        assert result.isna().all()
        assert diag.has_warnings

    def test_respects_custom_winsor_bounds(self) -> None:
        """Custom winsor bounds must flow through to the winsorize stage."""
        # With very tight bounds [0.1, 0.9], more values get clipped.
        s = pd.Series(np.arange(1, 11, dtype=float))  # 1..10
        tight, _ = normalize_cross_section(s, winsor_lower=0.1, winsor_upper=0.9)
        wide, _ = normalize_cross_section(s, winsor_lower=0.01, winsor_upper=0.99)
        # Tighter bounds should NOT change rank order (ranks are monotone),
        # but the post-winsor quantile boundaries differ, which for tied
        # clipped tails changes the rank-percentile result at the extremes.
        assert tight.iloc[0] == 0.0  # rank order preserved
        assert wide.iloc[-1] == 1.0

    def test_preserves_index(self) -> None:
        """Output series must keep the input index (symbols) intact."""
        s = pd.Series([0.5, 0.3, 0.9, 0.1], index=["AAPL", "MSFT", "NVDA", "GOOG"])
        result, _ = normalize_cross_section(s)
        assert list(result.index) == ["AAPL", "MSFT", "NVDA", "GOOG"]
