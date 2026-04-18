"""Unit tests for factor correlation analysis and deduplication."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyse_core.factor_correlation import (
    compute_factor_correlation_matrix,
    identify_redundant_factors,
    select_orthogonal_subset,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_feature_matrix(
    n_dates: int = 30,
    n_stocks: int = 50,
    n_factors: int = 5,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a synthetic feature matrix with independent factors."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n_dates)
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]
    factor_names = [f"factor_{i}" for i in range(n_factors)]

    records = []
    for dt in dates:
        for sym in symbols:
            row = {"date": dt, "symbol": sym}
            for fn in factor_names:
                row[fn] = rng.standard_normal()
            records.append(row)

    return pd.DataFrame(records)


def _make_correlated_feature_matrix(
    n_dates: int = 30,
    n_stocks: int = 50,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a feature matrix where factor_1 is nearly identical to factor_0."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2023-01-01", periods=n_dates)
    symbols = [f"SYM{i:03d}" for i in range(n_stocks)]

    records = []
    for dt in dates:
        for sym in symbols:
            base = rng.standard_normal()
            records.append(
                {
                    "date": dt,
                    "symbol": sym,
                    "factor_0": base,
                    "factor_1": base + rng.normal(0, 0.01),  # nearly identical
                    "factor_2": rng.standard_normal(),  # independent
                }
            )

    return pd.DataFrame(records)


# ── Tests ────────────────────────────────────────────────────────────────────


class TestCorrelationMatrixShape:
    """Correlation matrix should be n_factors x n_factors."""

    def test_correlation_matrix_shape(self):
        fm = _make_feature_matrix(n_dates=20, n_stocks=30, n_factors=4, seed=42)
        corr, diag = compute_factor_correlation_matrix(fm)

        assert corr.shape == (4, 4)
        assert list(corr.columns) == [f"factor_{i}" for i in range(4)]
        assert list(corr.index) == [f"factor_{i}" for i in range(4)]
        assert not diag.has_errors


class TestDiagonalIsOne:
    """Self-correlation should be exactly 1.0."""

    def test_diagonal_is_one(self):
        fm = _make_feature_matrix(n_dates=20, n_stocks=30, n_factors=5, seed=42)
        corr, diag = compute_factor_correlation_matrix(fm)

        for i in range(5):
            assert corr.iloc[i, i] == pytest.approx(1.0), (
                f"Diagonal element [{i},{i}] should be 1.0, got {corr.iloc[i, i]}"
            )


class TestIdentifyRedundantWithCorrelatedPair:
    """Two nearly identical factors should be flagged as redundant."""

    def test_identify_redundant_with_correlated_pair(self):
        fm = _make_correlated_feature_matrix(n_dates=30, n_stocks=50, seed=42)
        corr, _ = compute_factor_correlation_matrix(fm)
        redundant, diag = identify_redundant_factors(corr, max_correlation=0.50)

        # factor_0 and factor_1 are nearly identical -> should be flagged
        flagged_pairs = {(a, b) for a, b, _ in redundant}
        assert ("factor_0", "factor_1") in flagged_pairs, (
            f"Expected (factor_0, factor_1) in redundant pairs. Got: {redundant}"
        )

        # Verify the correlation value is high
        for a, b, c in redundant:
            if a == "factor_0" and b == "factor_1":
                assert c > 0.90, f"Expected high correlation, got {c:.4f}"


class TestSelectOrthogonalPicksBestICFirst:
    """Greedy selection should pick the highest-IC factor first."""

    def test_select_orthogonal_picks_best_ic_first(self):
        # Build a simple correlation matrix (all independent)
        factors = ["f_a", "f_b", "f_c"]
        corr = pd.DataFrame(
            np.eye(3),
            index=factors,
            columns=factors,
        )

        ic_scores = {"f_a": 0.01, "f_b": 0.05, "f_c": 0.03}

        selected, diag = select_orthogonal_subset(corr, ic_scores, max_correlation=0.50)

        # All factors are uncorrelated so all should be selected
        assert len(selected) == 3
        # First selected should be f_b (highest IC)
        assert selected[0] == "f_b"
        # Second should be f_c
        assert selected[1] == "f_c"
        assert not diag.has_errors


class TestSelectOrthogonalRemovesCorrelated:
    """Correlated factors should be excluded from the orthogonal subset."""

    def test_select_orthogonal_removes_correlated(self):
        # f_a and f_b are highly correlated; f_c is independent
        factors = ["f_a", "f_b", "f_c"]
        corr_vals = np.array(
            [
                [1.0, 0.90, 0.05],
                [0.90, 1.0, 0.10],
                [0.05, 0.10, 1.0],
            ]
        )
        corr = pd.DataFrame(corr_vals, index=factors, columns=factors)

        # f_a has higher IC than f_b
        ic_scores = {"f_a": 0.04, "f_b": 0.03, "f_c": 0.02}

        selected, diag = select_orthogonal_subset(corr, ic_scores, max_correlation=0.50)

        # f_a selected first (highest IC), f_b eliminated (corr > 0.50), f_c kept
        assert "f_a" in selected
        assert "f_b" not in selected  # eliminated by f_a
        assert "f_c" in selected
        assert selected[0] == "f_a"  # highest IC first
        assert len(selected) == 2
