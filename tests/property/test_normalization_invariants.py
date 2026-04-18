"""Property tests for normalization invariants.

These tests define the CONTRACT for rank_percentile, winsorize, z_score:
- rank_percentile output is always in [0, 1] for non-NaN values
- rank_percentile preserves order
- NaN positions are preserved from input to output
- Constant series maps to 0.5 for all values
- Single non-NaN value maps to 0.5
- winsorize clips at quantile boundaries
- z_score yields mean~0, std~1

Uses Hypothesis to generate arbitrary Series inputs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

try:
    from nyse_core.normalize import rank_percentile, winsorize, z_score
except ImportError:
    pytestmark = pytest.mark.skip(reason="nyse_core.normalize not yet available")
    rank_percentile = None  # type: ignore[assignment]
    winsorize = None  # type: ignore[assignment]
    z_score = None  # type: ignore[assignment]


# ── Strategies ───────────────────────────────────────────────────────────────

# Generate a list of floats with possible NaN values mixed in
_float_value = st.one_of(
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.just(float("nan")),
)

_series_strategy = st.lists(
    _float_value,
    min_size=1,
    max_size=200,
).map(lambda xs: pd.Series(xs, dtype=float))

# Series guaranteed to have at least one non-NaN value
_series_with_values = st.lists(
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    min_size=2,
    max_size=200,
).map(lambda xs: pd.Series(xs, dtype=float))

# Strategy matching the task specification: mixed floats with NaN/None
_mixed_float_list = st.lists(
    st.one_of(
        st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
        st.none(),
    ),
    min_size=1,
    max_size=500,
)


def _list_to_series(xs: list) -> pd.Series:
    """Convert a list with possible None/NaN to a float pd.Series."""
    return pd.Series([float("nan") if v is None else v for v in xs], dtype=float)


# ── Property: output in [0, 1] ──────────────────────────────────────────────


class TestRankPercentileOutputRange:
    """For any non-all-NaN Series, rank_percentile output is in [0, 1]."""

    @pytest.mark.property
    @given(data=_series_with_values)
    @settings(max_examples=200, deadline=None)
    def test_output_bounded_zero_one(self, data: pd.Series) -> None:
        """All non-NaN output values must be in [0.0, 1.0]."""
        result, _diag = rank_percentile(data)
        non_nan = result.dropna()
        if len(non_nan) > 0:
            assert non_nan.min() >= 0.0, f"Min value {non_nan.min()} < 0.0"
            assert non_nan.max() <= 1.0, f"Max value {non_nan.max()} > 1.0"

    @pytest.mark.property
    @given(data=_series_strategy)
    @settings(max_examples=200, deadline=None)
    def test_output_bounded_with_nans(self, data: pd.Series) -> None:
        """Even with NaN-heavy inputs, non-NaN outputs are in [0, 1]."""
        non_nan_count = data.notna().sum()
        assume(non_nan_count > 0)

        result, _diag = rank_percentile(data)
        non_nan_result = result.dropna()
        if len(non_nan_result) > 0:
            assert non_nan_result.min() >= 0.0
            assert non_nan_result.max() <= 1.0

    @pytest.mark.property
    @given(raw=_mixed_float_list)
    @settings(max_examples=100, deadline=None)
    def test_rank_percentile_output_in_0_1(self, raw: list) -> None:
        """For any non-NaN input value, output must be in [0, 1]."""
        series = _list_to_series(raw)
        assume(series.notna().sum() > 0)

        result, _diag = rank_percentile(series)
        non_nan = result.dropna()
        if len(non_nan) > 0:
            assert non_nan.min() >= 0.0
            assert non_nan.max() <= 1.0


# ── Property: rank_percentile preserves order ────────────────────────────────


class TestRankPercentilePreservesOrder:
    """If a > b in input, rank(a) >= rank(b) in output."""

    @pytest.mark.property
    @given(data=_series_with_values)
    @settings(max_examples=100, deadline=None)
    def test_rank_percentile_preserves_order(self, data: pd.Series) -> None:
        """Larger input values must not get smaller rank-percentile scores."""
        assume(len(data) >= 2)
        result, _diag = rank_percentile(data)

        non_nan_idx = data.dropna().index.tolist()
        for i in range(len(non_nan_idx)):
            for j in range(i + 1, len(non_nan_idx)):
                idx_i, idx_j = non_nan_idx[i], non_nan_idx[j]
                if data.iloc[idx_i] > data.iloc[idx_j]:
                    assert result.iloc[idx_i] >= result.iloc[idx_j], (
                        f"Order violated: input[{idx_i}]={data.iloc[idx_i]} > "
                        f"input[{idx_j}]={data.iloc[idx_j]}, but "
                        f"rank[{idx_i}]={result.iloc[idx_i]} < "
                        f"rank[{idx_j}]={result.iloc[idx_j]}"
                    )


# ── Property: NaN passthrough ────────────────────────────────────────────────


class TestRankPercentileNanPreservation:
    """rank_percentile preserves NaN positions from input to output."""

    @pytest.mark.property
    @given(data=_series_strategy)
    @settings(max_examples=200, deadline=None)
    def test_nan_positions_match(self, data: pd.Series) -> None:
        """Every NaN in the input must remain NaN in the output."""
        result, _diag = rank_percentile(data)

        input_nan_mask = data.isna()
        output_nan_mask = result.isna()

        # Every input NaN must be NaN in output
        assert (output_nan_mask[input_nan_mask]).all(), "Some input NaN positions became non-NaN in output"

    @pytest.mark.property
    @given(data=_series_with_values)
    @settings(max_examples=200, deadline=None)
    def test_non_nan_stays_non_nan(self, data: pd.Series) -> None:
        """Every non-NaN input value must produce a non-NaN output value."""
        result, _diag = rank_percentile(data)

        input_non_nan_mask = data.notna()
        output_non_nan_mask = result.notna()

        assert (output_non_nan_mask[input_non_nan_mask]).all(), (
            "Some non-NaN input values became NaN in output"
        )

    @pytest.mark.property
    @given(raw=_mixed_float_list)
    @settings(max_examples=100, deadline=None)
    def test_rank_percentile_nan_passthrough(self, raw: list) -> None:
        """NaN inputs must produce NaN outputs at the same positions."""
        series = _list_to_series(raw)
        result, _diag = rank_percentile(series)

        nan_mask = series.isna()
        assert result[nan_mask].isna().all(), "NaN inputs did not pass through as NaN"


# ── Property: single non-NaN value maps to 0.5 ──────────────────────────────


class TestRankPercentileSingleValue:
    """A single non-NaN value must map to 0.5."""

    @pytest.mark.property
    @given(
        value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        n_nans=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=100, deadline=None)
    def test_rank_percentile_single_value_is_0_5(
        self,
        value: float,
        n_nans: int,
    ) -> None:
        """Single non-NaN value in a series (possibly with NaNs) -> 0.5."""
        values = [value] + [float("nan")] * n_nans
        data = pd.Series(values, dtype=float)
        result, _diag = rank_percentile(data)

        non_nan = result.dropna()
        assert len(non_nan) == 1
        assert non_nan.iloc[0] == pytest.approx(0.5, abs=1e-10)


# ── Property: constant series maps to 0.5 ───────────────────────────────────


class TestRankPercentileConstantSeries:
    """rank_percentile of a constant series returns 0.5 for all values."""

    @pytest.mark.property
    @given(
        value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        n=st.integers(min_value=2, max_value=100),
    )
    @settings(max_examples=100, deadline=None)
    def test_constant_maps_to_half(self, value: float, n: int) -> None:
        """A Series where all non-NaN values are identical should map to 0.5."""
        data = pd.Series([value] * n, dtype=float)
        result, _diag = rank_percentile(data)
        non_nan = result.dropna()

        # All values in a constant series should be 0.5
        # (average of tied ranks scaled to [0, 1])
        assert len(non_nan) == n
        np.testing.assert_allclose(
            non_nan.values,
            0.5,
            atol=1e-10,
            err_msg=f"Constant series of {value} (n={n}) did not map to 0.5",
        )

    @pytest.mark.property
    @given(
        value=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        n=st.integers(min_value=2, max_value=50),
        n_nans=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=100, deadline=None)
    def test_constant_with_nans_maps_to_half(
        self,
        value: float,
        n: int,
        n_nans: int,
    ) -> None:
        """Constant values interspersed with NaNs should still map to 0.5."""
        values = [value] * n + [float("nan")] * n_nans
        data = pd.Series(values, dtype=float)
        result, _diag = rank_percentile(data)

        non_nan = result.dropna()
        assert len(non_nan) == n
        np.testing.assert_allclose(non_nan.values, 0.5, atol=1e-10)


# ── Property: winsorize clips at quantile boundaries ────────────────────────


class TestWinsorizeClipsAtQuantiles:
    """After winsorization, all non-NaN values are within the quantile range."""

    @pytest.mark.property
    @given(raw=_mixed_float_list)
    @settings(max_examples=100, deadline=None)
    def test_winsorize_clips_at_quantiles(self, raw: list) -> None:
        """Output values must be bounded by the quantile range of the input."""
        series = _list_to_series(raw)
        non_nan = series.dropna()
        assume(len(non_nan) >= 2)

        lower_q = 0.01
        upper_q = 0.99
        result, _diag = winsorize(series, lower=lower_q, upper=upper_q)

        low_val = float(non_nan.quantile(lower_q))
        high_val = float(non_nan.quantile(upper_q))

        result_non_nan = result.dropna()
        if len(result_non_nan) > 0:
            assert result_non_nan.min() >= low_val - 1e-10, (
                f"Min output {result_non_nan.min()} < lower bound {low_val}"
            )
            assert result_non_nan.max() <= high_val + 1e-10, (
                f"Max output {result_non_nan.max()} > upper bound {high_val}"
            )


# ── Property: z_score mean~0 std~1 ──────────────────────────────────────────


class TestZScoreMeanZeroStdOne:
    """z_score of non-NaN values should have mean~0 and std~1."""

    @pytest.mark.property
    @given(
        data=st.lists(
            st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
            min_size=3,
            max_size=500,
        ).map(lambda xs: pd.Series(xs, dtype=float))
    )
    @settings(max_examples=100, deadline=None)
    def test_z_score_mean_zero_std_one(self, data: pd.Series) -> None:
        """Z-scored non-NaN values must have mean~0 and std~1."""
        # Need at least 3 values and meaningful variance for a stable z-score.
        # Near-zero std makes z-score numerically unstable (large values / tiny std
        # amplifies floating-point error), so require a practical floor.
        assume(len(data) >= 3)
        assume(data.std(ddof=1) > 1e-6)

        result, _diag = z_score(data)
        non_nan = result.dropna()

        assert len(non_nan) == len(data)
        np.testing.assert_allclose(
            non_nan.mean(),
            0.0,
            atol=1e-6,
            err_msg=f"Z-scored mean {non_nan.mean():.8f} not ~0",
        )
        np.testing.assert_allclose(
            non_nan.std(ddof=1),
            1.0,
            atol=1e-6,
            err_msg=f"Z-scored std {non_nan.std(ddof=1):.8f} not ~1",
        )
