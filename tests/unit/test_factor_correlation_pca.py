"""Unit tests for PCA-based factor deduplication."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.factor_correlation import (
    pca_factor_decomposition,
    select_factors_by_pca,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_feature_matrix(
    n_rows: int = 200,
    n_factors: int = 5,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a simple feature matrix (rows x factors)."""
    rng = np.random.default_rng(seed)
    factor_names = [f"factor_{i}" for i in range(n_factors)]
    data = rng.uniform(0, 1, size=(n_rows, n_factors))
    return pd.DataFrame(data, columns=factor_names)


def _make_correlated_matrix(
    n_rows: int = 200,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a feature matrix with 2 independent dimensions + redundant copies.

    factor_0 and factor_1 are independent.
    factor_2 is nearly identical to factor_0.
    factor_3 is nearly identical to factor_1.
    factor_4 is independent noise.
    """
    rng = np.random.default_rng(seed)
    f0 = rng.uniform(0, 1, size=n_rows)
    f1 = rng.uniform(0, 1, size=n_rows)
    f2 = f0 + rng.normal(0, 0.01, size=n_rows)  # copy of f0
    f3 = f1 + rng.normal(0, 0.01, size=n_rows)  # copy of f1
    f4 = rng.uniform(0, 1, size=n_rows)  # independent

    return pd.DataFrame(
        {
            "factor_0": f0,
            "factor_1": f1,
            "factor_2": f2,
            "factor_3": f3,
            "factor_4": f4,
        }
    )


# ── PCA Decomposition Tests ─────────────────────────────────────────────────


class TestPCABasicDecomposition:
    """PCA should return transformed matrix and info dict."""

    def test_pca_basic_decomposition(self):
        fm = _make_feature_matrix(n_rows=200, n_factors=5, seed=42)
        transformed, info, diag = pca_factor_decomposition(fm)

        assert not diag.has_errors
        assert transformed.shape[0] == 200
        assert "n_components" in info
        assert "explained_variance_ratio" in info
        assert "loadings" in info
        assert "cumulative_variance" in info
        assert info["n_components"] > 0
        assert info["n_components"] <= 5


class TestPCAVarianceThreshold:
    """PCA with high threshold should keep more components."""

    def test_pca_variance_threshold(self):
        fm = _make_feature_matrix(n_rows=200, n_factors=5, seed=42)

        # Low threshold -> fewer components
        _, info_low, _ = pca_factor_decomposition(fm, variance_threshold=0.50)
        # High threshold -> more components
        _, info_high, _ = pca_factor_decomposition(fm, variance_threshold=0.99)

        assert info_low["n_components"] <= info_high["n_components"]


class TestPCAWithNaNRows:
    """Rows with NaN should be dropped before PCA."""

    def test_pca_with_nan_rows(self):
        fm = _make_feature_matrix(n_rows=200, n_factors=3, seed=42)
        # Inject NaN in some rows
        fm.iloc[0, 0] = float("nan")
        fm.iloc[5, 1] = float("nan")
        fm.iloc[10, 2] = float("nan")

        transformed, info, diag = pca_factor_decomposition(fm)

        assert not diag.has_errors
        # Rows with NaN should be dropped
        assert transformed.shape[0] == 197  # 200 - 3 NaN rows
        assert info["n_components"] > 0


class TestPCASingleFactor:
    """Single factor should produce 1 component."""

    def test_pca_single_factor(self):
        fm = _make_feature_matrix(n_rows=100, n_factors=1, seed=42)
        transformed, info, diag = pca_factor_decomposition(fm)

        assert info["n_components"] == 1
        assert transformed.shape[1] == 1
        assert not diag.has_errors


class TestPCALoadingsShape:
    """Loadings matrix should be (n_factors x n_components)."""

    def test_pca_loadings_shape(self):
        n_factors = 5
        fm = _make_feature_matrix(n_rows=200, n_factors=n_factors, seed=42)
        _, info, diag = pca_factor_decomposition(fm, n_components=3)

        loadings = info["loadings"]
        assert isinstance(loadings, pd.DataFrame)
        assert loadings.shape[0] == n_factors  # rows = original factors
        assert loadings.shape[1] == 3  # columns = requested PCs


# ── PCA Factor Selection Tests ───────────────────────────────────────────────


class TestSelectFactorsByPCABasic:
    """Select factors using PCA-informed deduplication."""

    def test_select_factors_by_pca_basic(self):
        fm = _make_correlated_matrix(n_rows=200, seed=42)
        ic_scores = {
            "factor_0": 0.05,
            "factor_1": 0.04,
            "factor_2": 0.03,
            "factor_3": 0.02,
            "factor_4": 0.01,
        }

        selected, diag = select_factors_by_pca(fm, ic_scores, max_factors=8)

        assert not diag.has_errors
        assert len(selected) > 0
        assert len(selected) <= 5  # can't select more than available


class TestSelectFactorsByPCAMaxFactors:
    """max_factors limits the output."""

    def test_select_factors_by_pca_max_factors(self):
        fm = _make_feature_matrix(n_rows=200, n_factors=10, seed=42)
        ic_scores = {f"factor_{i}": 0.05 - i * 0.005 for i in range(10)}

        selected, diag = select_factors_by_pca(fm, ic_scores, max_factors=3)

        assert len(selected) <= 3


class TestSelectFactorsByPCAEmpty:
    """Empty matrix should return empty selection."""

    def test_select_factors_by_pca_empty(self):
        fm = pd.DataFrame()
        ic_scores: dict[str, float] = {}

        selected, diag = select_factors_by_pca(fm, ic_scores, max_factors=5)

        assert selected == []
        assert diag.has_warnings
