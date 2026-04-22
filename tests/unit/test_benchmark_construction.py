"""Unit tests for ``nyse_core.benchmark_construction``.

Two helpers live here — ``compute_sector_neutral_returns`` (iter-2) and
``compute_characteristic_matched_benchmark`` (iter-4). The sector-neutral
helper removes GICS-composition tilt; the characteristic-matched helper
removes style-composition tilt (size, value, momentum, etc.). Both return
``(result, Diagnostics)`` and degrade gracefully on degenerate inputs rather
than raising.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyse_core.benchmark_construction import (
    compute_characteristic_matched_benchmark,
    compute_sector_neutral_returns,
)


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


# ─── Characteristic-matched benchmark tests (iter-4) ──────────────────────────
#
# The helper buckets the universe by a characteristic at each date, computes
# each bucket's equal-weight return, then returns the bucket whose mean is
# matched to the long-leg's weighted-mean bucket index (rounded to nearest
# integer). Correctness reduces to:
#   1. Bucketing is deterministic (rank-then-qcut breaks ties).
#   2. Weighted-mean bucket index respects long-leg weights.
#   3. Degenerate inputs return a NaN series with warnings — never raise.
#   4. Output index equals ``daily_returns.index`` exactly.
# ──────────────────────────────────────────────────────────────────────────────


def _char_panel(date: pd.Timestamp, mapping: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [date] * len(mapping),
            "symbol": list(mapping.keys()),
            "value": list(mapping.values()),
        }
    )


def _weights(date: pd.Timestamp, mapping: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [date] * len(mapping),
            "symbol": list(mapping.keys()),
            "weight": list(mapping.values()),
        }
    )


class TestCharMatchedHappyPath:
    def test_long_leg_in_top_bucket_matches_top_bucket_return(self) -> None:
        # 5 symbols with characteristic 10..50 → buckets 1..5 (one symbol each).
        # Returns 0.05..0.25 → bucket means equal the per-symbol return.
        # Long-leg on E only → weighted-mean bucket = 5 → matched = 5.
        dt = pd.Timestamp("2020-01-03")
        panel = pd.DataFrame(
            [[0.05, 0.10, 0.15, 0.20, 0.25]],
            index=pd.DatetimeIndex([dt]),
            columns=list("ABCDE"),
        )
        char = _char_panel(dt, {"A": 10, "B": 20, "C": 30, "D": 40, "E": 50})
        w = _weights(dt, {"E": 1.0})

        bench, diag = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=5)

        assert bench.iloc[0] == pytest.approx(0.25, abs=1e-12)
        assert bench.name == "char_matched"
        assert any("char_matched benchmark built" in m.message for m in diag.messages)

    def test_long_leg_in_bottom_bucket_matches_bottom_bucket_return(self) -> None:
        dt = pd.Timestamp("2020-01-03")
        panel = pd.DataFrame(
            [[0.05, 0.10, 0.15, 0.20, 0.25]],
            index=pd.DatetimeIndex([dt]),
            columns=list("ABCDE"),
        )
        char = _char_panel(dt, {"A": 10, "B": 20, "C": 30, "D": 40, "E": 50})
        w = _weights(dt, {"A": 1.0})

        bench, _ = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=5)

        assert bench.iloc[0] == pytest.approx(0.05, abs=1e-12)

    def test_long_leg_uniform_over_universe_matches_middle_bucket(self) -> None:
        # 5 symbols, 5 buckets, linearly spaced returns. Long-leg uniform →
        # weighted-mean bucket = 3 → benchmark = middle-bucket return = 0.15.
        # For symmetric linearly-spaced returns, bucket-3 mean also equals the
        # universe mean (0.15), recovering the "reduces to universe-mean"
        # invariant from the spec.
        dt = pd.Timestamp("2020-01-03")
        panel = pd.DataFrame(
            [[0.05, 0.10, 0.15, 0.20, 0.25]],
            index=pd.DatetimeIndex([dt]),
            columns=list("ABCDE"),
        )
        char = _char_panel(dt, {"A": 10, "B": 20, "C": 30, "D": 40, "E": 50})
        w = _weights(dt, {s: 0.2 for s in "ABCDE"})

        bench, _ = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=5)

        universe_mean = float(panel.iloc[0].mean())
        assert bench.iloc[0] == pytest.approx(universe_mean, abs=1e-12)
        assert bench.iloc[0] == pytest.approx(0.15, abs=1e-12)

    def test_monotone_characteristic_multi_symbol_bucket(self) -> None:
        # 10 symbols, 5 buckets (2 per bucket). Long-leg only on the top-2
        # symbols → matched = 5 → benchmark = mean of top-2 returns.
        dt = pd.Timestamp("2020-01-03")
        symbols = [f"S{i:02d}" for i in range(10)]
        returns = [0.01 * (i + 1) for i in range(10)]
        panel = pd.DataFrame([returns], index=pd.DatetimeIndex([dt]), columns=symbols)
        char = _char_panel(dt, {s: float(i) for i, s in enumerate(symbols)})
        w = _weights(dt, {symbols[-1]: 0.5, symbols[-2]: 0.5})

        bench, _ = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=5)

        expected = float(np.mean([returns[-1], returns[-2]]))
        assert bench.iloc[0] == pytest.approx(expected, abs=1e-12)

    def test_nan_return_dropped_within_bucket(self) -> None:
        # 4 symbols, 2 buckets: {A,B} bucket 1, {C,D} bucket 2.
        # B has NaN return → bucket 1 mean uses only A.
        dt = pd.Timestamp("2020-01-03")
        panel = pd.DataFrame(
            [[0.10, np.nan, 0.20, 0.30]],
            index=pd.DatetimeIndex([dt]),
            columns=list("ABCD"),
        )
        char = _char_panel(dt, {"A": 1, "B": 2, "C": 3, "D": 4})
        w = _weights(dt, {"C": 1.0})

        bench, _ = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=2)

        # Long-leg on C → bucket 2 mean = mean(C, D) = 0.25.
        assert bench.iloc[0] == pytest.approx(0.25, abs=1e-12)


class TestCharMatchedDegenerateInputs:
    def test_empty_daily_returns_returns_empty_series(self) -> None:
        char = _char_panel(pd.Timestamp("2020-01-03"), {"A": 1.0})
        w = _weights(pd.Timestamp("2020-01-03"), {"A": 1.0})

        bench, diag = compute_characteristic_matched_benchmark(pd.DataFrame(), char, w, n_buckets=5)

        assert bench.empty
        assert any("daily_returns is empty" in m.message for m in diag.messages)

    def test_empty_characteristic_panel_returns_nan_series(self) -> None:
        idx = _dates(3)
        panel = pd.DataFrame({"A": [0.1, 0.2, 0.3]}, index=idx)
        char = pd.DataFrame(columns=["date", "symbol", "value"])
        w = _weights(idx[0], {"A": 1.0})

        bench, diag = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=5)

        assert bench.index.equals(idx)
        assert bench.isna().all()
        assert any("characteristic_panel is empty" in m.message for m in diag.messages)

    def test_empty_long_leg_weights_returns_nan_series(self) -> None:
        idx = _dates(3)
        panel = pd.DataFrame({"A": [0.1, 0.2, 0.3]}, index=idx)
        char = _char_panel(idx[0], {"A": 1.0})
        w = pd.DataFrame(columns=["date", "symbol", "weight"])

        bench, diag = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=5)

        assert bench.index.equals(idx)
        assert bench.isna().all()
        assert any("long_leg_weights is empty" in m.message for m in diag.messages)

    def test_missing_characteristic_column_returns_nan_series(self) -> None:
        idx = _dates(3)
        panel = pd.DataFrame({"A": [0.1, 0.2, 0.3]}, index=idx)
        # Missing 'value' column.
        bad_char = pd.DataFrame({"date": [idx[0]], "symbol": ["A"]})
        w = _weights(idx[0], {"A": 1.0})

        bench, diag = compute_characteristic_matched_benchmark(panel, bad_char, w, n_buckets=5)

        assert bench.index.equals(idx)
        assert bench.isna().all()
        assert any("missing required columns" in m.message for m in diag.messages)

    def test_missing_weight_column_returns_nan_series(self) -> None:
        idx = _dates(3)
        panel = pd.DataFrame({"A": [0.1, 0.2, 0.3]}, index=idx)
        char = _char_panel(idx[0], {"A": 1.0})
        # Missing 'weight' column.
        bad_w = pd.DataFrame({"date": [idx[0]], "symbol": ["A"]})

        bench, diag = compute_characteristic_matched_benchmark(panel, char, bad_w, n_buckets=5)

        assert bench.index.equals(idx)
        assert bench.isna().all()
        assert any("missing required columns" in m.message for m in diag.messages)

    def test_nbuckets_zero_returns_empty_series_with_warning(self) -> None:
        idx = _dates(1)
        panel = pd.DataFrame({"A": [0.1], "B": [0.2]}, index=idx)
        char = _char_panel(idx[0], {"A": 1.0, "B": 2.0})
        w = _weights(idx[0], {"A": 1.0})

        bench, diag = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=0)

        assert bench.empty
        assert any("n_buckets=0 must be >= 1" in m.message for m in diag.messages)

    def test_zero_weight_sum_date_yields_nan(self) -> None:
        # Long-leg weights cancel to zero → that date degrades to NaN.
        idx = _dates(1)
        panel = pd.DataFrame(
            [[0.05, 0.10, 0.15, 0.20, 0.25]],
            index=idx,
            columns=list("ABCDE"),
        )
        char = _char_panel(idx[0], {"A": 10, "B": 20, "C": 30, "D": 40, "E": 50})
        w = _weights(idx[0], {"A": 1.0, "E": -1.0})  # sums to zero

        bench, _ = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=5)

        assert np.isnan(bench.iloc[0])


class TestCharMatchedEdgeCases:
    def test_single_bucket_degeneracy_returns_universe_mean(self) -> None:
        # n_buckets=1 forces everyone into one bucket → benchmark = universe mean.
        dt = pd.Timestamp("2020-01-03")
        panel = pd.DataFrame(
            [[0.10, 0.20, 0.30]],
            index=pd.DatetimeIndex([dt]),
            columns=list("ABC"),
        )
        char = _char_panel(dt, {"A": 1.0, "B": 2.0, "C": 3.0})
        w = _weights(dt, {"A": 1.0})

        bench, _ = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=1)

        assert bench.iloc[0] == pytest.approx(0.20, abs=1e-12)

    def test_unmapped_long_leg_symbol_excluded_from_bucket_mean(self) -> None:
        # Long-leg includes 'Z' which has no characteristic value on this date.
        # 'Z' should be dropped from the weighted-mean bucket calculation.
        dt = pd.Timestamp("2020-01-03")
        panel = pd.DataFrame(
            [[0.10, 0.20, 0.30]],
            index=pd.DatetimeIndex([dt]),
            columns=list("ABC"),
        )
        char = _char_panel(dt, {"A": 1.0, "B": 2.0, "C": 3.0})
        w = _weights(dt, {"B": 0.5, "Z": 0.5})

        bench, _ = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=3)

        # Only B's weight counts → weighted-mean bucket = 2 → benchmark = B's return.
        assert bench.iloc[0] == pytest.approx(0.20, abs=1e-12)

    def test_output_index_matches_input_index_exactly(self) -> None:
        idx = _dates(10)
        rng = np.random.default_rng(0)
        panel = pd.DataFrame(
            rng.normal(0, 0.01, size=(10, 5)),
            index=idx,
            columns=list("ABCDE"),
        )
        char_rows = []
        w_rows = []
        for dt in idx:
            char_rows.append(_char_panel(dt, {s: float(i) for i, s in enumerate("ABCDE")}))
            w_rows.append(_weights(dt, {"E": 1.0}))
        char = pd.concat(char_rows, ignore_index=True)
        w = pd.concat(w_rows, ignore_index=True)

        bench, _ = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=5)

        assert bench.index.equals(idx)
        assert bench.name == "char_matched"
        assert bench.notna().all()  # every date has a usable match

    def test_missing_characteristic_on_some_dates_degrades_to_nan(self) -> None:
        # Characteristic panel covers dates 0 and 2 only → date 1 is NaN in output.
        idx = _dates(3)
        panel = pd.DataFrame(
            {"A": [0.10, 0.11, 0.12], "B": [0.20, 0.21, 0.22], "C": [0.30, 0.31, 0.32]},
            index=idx,
        )
        char = pd.concat(
            [
                _char_panel(idx[0], {"A": 1, "B": 2, "C": 3}),
                _char_panel(idx[2], {"A": 1, "B": 2, "C": 3}),
            ],
            ignore_index=True,
        )
        w = pd.concat(
            [
                _weights(idx[0], {"C": 1.0}),
                _weights(idx[1], {"C": 1.0}),
                _weights(idx[2], {"C": 1.0}),
            ],
            ignore_index=True,
        )

        bench, _ = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=3)

        # date 0 and 2 should be populated; date 1 is NaN (no characteristic data).
        assert not np.isnan(bench.iloc[0])
        assert np.isnan(bench.iloc[1])
        assert not np.isnan(bench.iloc[2])

    def test_matched_bucket_empty_returns_falls_back_to_nearest(self) -> None:
        # 3 buckets. Returns for bucket 2's only symbol are NaN. Long-leg
        # weighted-mean bucket rounds to 2 but bucket 2 has no returns →
        # fallback to bucket 1 or 3 (whichever is nearest; tie → sorted nearest).
        dt = pd.Timestamp("2020-01-03")
        panel = pd.DataFrame(
            [[0.10, np.nan, 0.30]],
            index=pd.DatetimeIndex([dt]),
            columns=list("ABC"),
        )
        char = _char_panel(dt, {"A": 1.0, "B": 2.0, "C": 3.0})
        w = _weights(dt, {"B": 1.0})  # forces matched=2

        bench, _ = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=3)

        # Matched bucket 2 has no observed returns. Nearest observed bucket is
        # 1 (|1-2|=1) tied with 3 (|3-2|=1); the min() of a tie picks the
        # smaller value deterministically → bucket 1 return = 0.10.
        assert bench.iloc[0] == pytest.approx(0.10, abs=1e-12)

    def test_drop_duplicate_char_rows_keeps_first(self) -> None:
        dt = pd.Timestamp("2020-01-03")
        panel = pd.DataFrame(
            [[0.10, 0.20, 0.30]],
            index=pd.DatetimeIndex([dt]),
            columns=list("ABC"),
        )
        # Two rows for 'A': first value 1.0, duplicate value 99.0 (would
        # otherwise push A to the top bucket).
        char = pd.DataFrame(
            {
                "date": [dt, dt, dt, dt],
                "symbol": ["A", "A", "B", "C"],
                "value": [1.0, 99.0, 2.0, 3.0],
            }
        )
        w = _weights(dt, {"A": 1.0})

        bench, _ = compute_characteristic_matched_benchmark(panel, char, w, n_buckets=3)

        # With first-occurrence dedup, A is bucket 1. Benchmark = 0.10.
        # If dedup had kept 99.0, A would be bucket 3 → benchmark = 0.30.
        assert bench.iloc[0] == pytest.approx(0.10, abs=1e-12)
