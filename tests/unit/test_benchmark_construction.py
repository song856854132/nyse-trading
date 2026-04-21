"""Unit tests for ``nyse_core.benchmark_construction.compute_sector_neutral_returns``.

The goal of this helper is to remove sector-composition tilt from a diagnostic
benchmark. Correctness reduces to three invariants:

1. Equal-weight within sector, then equal-weight across sectors — two-stage mean.
2. Unclassified symbols and NaN returns are dropped, not imputed.
3. Degenerate inputs (empty panel, empty map, no overlap) return a NaN series
   with warnings — never raise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyse_core.benchmark_construction import compute_sector_neutral_returns


def _dates(n: int, start: str = "2020-01-03") -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=n, freq="W-FRI")


class TestHappyPath:
    def test_two_stage_mean_matches_manual_computation(self) -> None:
        # 4 symbols, 2 sectors, 3 dates. Hand-computed benchmark.
        idx = _dates(3)
        panel = pd.DataFrame(
            {
                "A": [0.10, 0.20, 0.30],  # Tech
                "B": [0.00, 0.10, 0.20],  # Tech
                "C": [-0.10, 0.00, 0.10],  # Finance
                "D": [-0.20, -0.10, 0.00],  # Finance
            },
            index=idx,
        )
        sectors = pd.Series({"A": "Tech", "B": "Tech", "C": "Finance", "D": "Finance"})

        bench, diag = compute_sector_neutral_returns(panel, sectors)

        # Tech sector means: [0.05, 0.15, 0.25]; Finance: [-0.15, -0.05, 0.05]
        # Benchmark = mean of sector means: [-0.05, 0.05, 0.15]
        expected = pd.Series([-0.05, 0.05, 0.15], index=idx, name="sector_neutral")
        pd.testing.assert_series_equal(bench, expected, check_exact=False, rtol=1e-12)
        assert any("sector_neutral benchmark built" in m.message for m in diag.messages)

    def test_unequal_sector_sizes_equal_weight_across_sectors(self) -> None:
        # 5 symbols, 2 sectors: 3 Tech + 2 Finance. Benchmark must still give
        # each sector 50% weight — unequal symbol counts must not bias.
        idx = _dates(1)
        panel = pd.DataFrame(
            {"A": [0.10], "B": [0.20], "C": [0.30], "D": [-0.10], "E": [-0.20]},
            index=idx,
        )
        sectors = pd.Series({"A": "T", "B": "T", "C": "T", "D": "F", "E": "F"})

        bench, _ = compute_sector_neutral_returns(panel, sectors)

        # Tech mean = 0.20, Finance mean = -0.15. Benchmark = 0.025.
        assert bench.iloc[0] == pytest.approx(0.025, abs=1e-12)

    def test_nan_returns_dropped_within_sector(self) -> None:
        idx = _dates(1)
        panel = pd.DataFrame({"A": [np.nan], "B": [0.20], "C": [-0.10]}, index=idx)
        sectors = pd.Series({"A": "T", "B": "T", "C": "F"})

        bench, _ = compute_sector_neutral_returns(panel, sectors)

        # Tech mean ignoring NaN A = 0.20; Finance = -0.10. Benchmark = 0.05.
        assert bench.iloc[0] == pytest.approx(0.05, abs=1e-12)


class TestUnclassifiedSymbols:
    def test_unmapped_symbols_excluded_with_info_message(self) -> None:
        idx = _dates(1)
        panel = pd.DataFrame({"A": [0.10], "B": [0.20], "X": [5.00]}, index=idx)
        # X has no sector — must be excluded.
        sectors = pd.Series({"A": "T", "B": "T"})

        bench, diag = compute_sector_neutral_returns(panel, sectors)

        # Only A and B contribute: Tech mean = 0.15. Benchmark = 0.15 (single sector).
        assert bench.iloc[0] == pytest.approx(0.15, abs=1e-12)
        assert any("no sector assignment" in m.message for m in diag.messages)

    def test_nan_sector_label_treated_as_unclassified(self) -> None:
        idx = _dates(1)
        panel = pd.DataFrame({"A": [0.10], "B": [0.20], "C": [0.30]}, index=idx)
        sectors = pd.Series({"A": "T", "B": "T", "C": np.nan})

        bench, _ = compute_sector_neutral_returns(panel, sectors)

        # C dropped; benchmark = Tech mean = 0.15.
        assert bench.iloc[0] == pytest.approx(0.15, abs=1e-12)


class TestDegenerateInputs:
    def test_empty_panel_returns_empty_series(self) -> None:
        panel = pd.DataFrame()
        sectors = pd.Series({"A": "T"})

        bench, diag = compute_sector_neutral_returns(panel, sectors)
        assert bench.empty
        assert any("daily_returns is empty" in m.message for m in diag.messages)

    def test_empty_sector_map_returns_all_nan_series(self) -> None:
        idx = _dates(3)
        panel = pd.DataFrame({"A": [0.1, 0.2, 0.3]}, index=idx)
        sectors = pd.Series(dtype=str)

        bench, diag = compute_sector_neutral_returns(panel, sectors)
        assert bench.index.equals(idx)
        assert bench.isna().all()
        assert any("sector_map is empty" in m.message for m in diag.messages)

    def test_no_overlap_returns_all_nan_series(self) -> None:
        idx = _dates(3)
        panel = pd.DataFrame({"A": [0.1, 0.2, 0.3]}, index=idx)
        sectors = pd.Series({"Z": "T"})  # no overlap with panel

        bench, diag = compute_sector_neutral_returns(panel, sectors)
        assert bench.index.equals(idx)
        assert bench.isna().all()
        assert any("no overlap" in m.message for m in diag.messages)

    def test_day_with_all_nan_returns_degrades_to_nan(self) -> None:
        idx = _dates(3)
        panel = pd.DataFrame(
            {"A": [0.1, np.nan, 0.3], "B": [0.2, np.nan, 0.4]},
            index=idx,
        )
        sectors = pd.Series({"A": "T", "B": "T"})

        bench, _ = compute_sector_neutral_returns(panel, sectors)
        assert bench.iloc[0] == pytest.approx(0.15, abs=1e-12)
        assert np.isnan(bench.iloc[1])
        assert bench.iloc[2] == pytest.approx(0.35, abs=1e-12)


class TestIndexAlignment:
    def test_output_index_matches_input_index_exactly(self) -> None:
        idx = _dates(10)
        panel = pd.DataFrame(
            np.random.default_rng(0).normal(0, 0.01, size=(10, 5)),
            index=idx,
            columns=list("ABCDE"),
        )
        sectors = pd.Series({"A": "X", "B": "X", "C": "Y", "D": "Y", "E": "Z"})

        bench, _ = compute_sector_neutral_returns(panel, sectors)
        assert bench.index.equals(idx)
        assert bench.name == "sector_neutral"
