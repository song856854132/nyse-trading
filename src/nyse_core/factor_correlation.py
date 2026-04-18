"""Factor deduplication via cross-sectional correlation analysis.

Provides tools to identify redundant factors and select an orthogonal subset
based on IC ranking and pairwise correlation thresholds.

All functions are pure -- no I/O, no logging.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from nyse_core.contracts import Diagnostics

_MOD = "factor_correlation"


def compute_factor_correlation_matrix(
    feature_matrix: pd.DataFrame,
) -> tuple[pd.DataFrame, Diagnostics]:
    """Cross-sectional correlation matrix averaged over time.

    For each rebalance date: compute Spearman rank correlation between all
    factor pairs across the stock cross-section.

    Parameters
    ----------
    feature_matrix : pd.DataFrame
        MultiIndex (date, symbol) or columns: date, symbol, factor1, factor2, ...
        If columns include 'date' and 'symbol', they are set as a MultiIndex.

    Returns
    -------
    tuple[pd.DataFrame, Diagnostics]
        (average correlation matrix with factors as rows and columns, diagnostics).
    """
    diag = Diagnostics()
    src = f"{_MOD}.compute_factor_correlation_matrix"

    df = feature_matrix.copy()

    # Handle flat DataFrame with date/symbol columns
    if "date" in df.columns and "symbol" in df.columns:
        df = df.set_index(["date", "symbol"])

    factor_names = list(df.columns)
    n_factors = len(factor_names)

    if n_factors < 2:
        diag.warning(src, f"Only {n_factors} factor(s) — need >= 2 for correlation.")
        corr = pd.DataFrame(np.eye(n_factors), index=factor_names, columns=factor_names)
        return corr, diag

    # Get unique dates from the index
    dates = df.index.get_level_values(0).unique()

    # Accumulate correlation matrices
    corr_sum = np.zeros((n_factors, n_factors))
    n_valid_dates = 0

    for dt in dates:
        try:
            day_data = df.loc[dt]
        except KeyError:
            continue

        # Drop rows with any NaN
        day_clean = day_data.dropna()

        if len(day_clean) < 3:
            continue

        # Compute Spearman correlation for this cross-section
        corr_matrix = day_clean.corr(method="spearman").values

        if np.any(np.isnan(corr_matrix)):
            # Fill NaN correlations with 0 for averaging
            corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)

        corr_sum += corr_matrix
        n_valid_dates += 1

    if n_valid_dates == 0:
        diag.warning(src, "No valid dates for correlation computation.")
        corr = pd.DataFrame(np.eye(n_factors), index=factor_names, columns=factor_names)
        return corr, diag

    avg_corr = corr_sum / n_valid_dates

    # Force diagonal to exactly 1.0
    np.fill_diagonal(avg_corr, 1.0)

    result = pd.DataFrame(avg_corr, index=factor_names, columns=factor_names)

    diag.info(
        src,
        f"Averaged correlation over {n_valid_dates} dates for {n_factors} factors.",
    )
    return result, diag


def identify_redundant_factors(
    corr_matrix: pd.DataFrame,
    max_correlation: float = 0.50,
) -> tuple[list[tuple[str, str, float]], Diagnostics]:
    """Find factor pairs exceeding the correlation threshold.

    Parameters
    ----------
    corr_matrix : pd.DataFrame
        Square correlation matrix (factor x factor).
    max_correlation : float
        Absolute correlation threshold (default 0.50).

    Returns
    -------
    tuple[list[tuple[str, str, float]], Diagnostics]
        (list of (factor_a, factor_b, correlation) tuples, diagnostics).
    """
    diag = Diagnostics()
    src = f"{_MOD}.identify_redundant_factors"

    factor_names = list(corr_matrix.columns)
    n = len(factor_names)
    redundant: list[tuple[str, str, float]] = []

    for i in range(n):
        for j in range(i + 1, n):
            corr_val = abs(corr_matrix.iloc[i, j])
            if corr_val > max_correlation:
                redundant.append((factor_names[i], factor_names[j], float(corr_val)))

    diag.info(
        src,
        f"Found {len(redundant)} redundant pairs (|corr| > {max_correlation}).",
    )
    return redundant, diag


def select_orthogonal_subset(
    corr_matrix: pd.DataFrame,
    factor_ic_scores: dict[str, float],
    max_correlation: float = 0.50,
) -> tuple[list[str], Diagnostics]:
    """Greedy selection: pick factors by IC, remove correlated neighbors.

    Algorithm:
      1. Sort factors by absolute IC descending
      2. Select top factor
      3. Remove all factors correlated > max_correlation with selected
      4. Repeat until no factors remain

    Parameters
    ----------
    corr_matrix : pd.DataFrame
        Square correlation matrix (factor x factor).
    factor_ic_scores : dict[str, float]
        Mapping of factor_name -> IC mean (used for ranking).
    max_correlation : float
        Maximum absolute correlation allowed between selected factors.

    Returns
    -------
    tuple[list[str], Diagnostics]
        (list of selected factor names in priority order, diagnostics).
    """
    diag = Diagnostics()
    src = f"{_MOD}.select_orthogonal_subset"

    # Only consider factors present in both the correlation matrix and IC scores
    available = [f for f in corr_matrix.columns if f in factor_ic_scores]

    if not available:
        diag.warning(src, "No factors available for selection.")
        return [], diag

    # Sort by absolute IC descending
    ranked = sorted(available, key=lambda f: abs(factor_ic_scores[f]), reverse=True)

    selected: list[str] = []
    eliminated: set[str] = set()

    for factor in ranked:
        if factor in eliminated:
            continue

        selected.append(factor)

        # Eliminate all remaining factors correlated > threshold
        for other in ranked:
            if other == factor or other in eliminated or other in selected:
                continue
            if other in corr_matrix.columns and factor in corr_matrix.index:
                corr_val = abs(corr_matrix.loc[factor, other])
                if corr_val > max_correlation:
                    eliminated.add(other)

    diag.info(
        src,
        f"Selected {len(selected)} orthogonal factors from {len(available)} candidates.",
    )
    return selected, diag


# ── PCA-Based Factor Deduplication ──────────────────────────────────────────


def pca_factor_decomposition(
    feature_matrix: pd.DataFrame,
    n_components: int | None = None,
    variance_threshold: float = 0.95,
) -> tuple[pd.DataFrame, dict[str, Any], Diagnostics]:
    """PCA decomposition of factor matrix.

    Parameters
    ----------
    feature_matrix : pd.DataFrame
        (date x symbol) rows x factor columns, values in [0,1].
    n_components : int | None
        If None, select enough to explain variance_threshold.
    variance_threshold : float
        Cumulative variance ratio to explain (default 95%).

    Returns
    -------
    tuple[pd.DataFrame, dict, Diagnostics]
        (transformed_matrix with PC columns,
         info_dict with keys: n_components, explained_variance_ratio,
         loadings (DataFrame: factor x PC), cumulative_variance),
         diagnostics)
    """
    diag = Diagnostics()
    src = f"{_MOD}.pca_factor_decomposition"

    if feature_matrix.empty or feature_matrix.shape[1] == 0:
        diag.warning(src, "Empty feature matrix provided.")
        empty_info: dict[str, Any] = {
            "n_components": 0,
            "explained_variance_ratio": [],
            "loadings": pd.DataFrame(),
            "cumulative_variance": [],
        }
        return pd.DataFrame(), empty_info, diag

    # Drop rows with any NaN
    clean = feature_matrix.dropna()
    n_dropped = len(feature_matrix) - len(clean)
    if n_dropped > 0:
        diag.info(src, f"Dropped {n_dropped} rows with NaN values.")

    if len(clean) < 2:
        diag.warning(src, "Insufficient rows after dropping NaN (need >= 2).")
        empty_info = {
            "n_components": 0,
            "explained_variance_ratio": [],
            "loadings": pd.DataFrame(),
            "cumulative_variance": [],
        }
        return pd.DataFrame(), empty_info, diag

    factor_names = list(clean.columns)
    max_components = min(len(clean), len(factor_names))

    if n_components is not None:
        n_comp = min(n_components, max_components)
    else:
        # First fit with all components to find how many we need
        pca_full = PCA(n_components=max_components)
        pca_full.fit(clean.values)
        cumvar = np.cumsum(pca_full.explained_variance_ratio_)

        # Find smallest k such that cumulative variance >= threshold
        n_comp = int(np.searchsorted(cumvar, variance_threshold) + 1)
        n_comp = min(n_comp, max_components)

    # Fit PCA with selected number of components
    pca = PCA(n_components=n_comp)
    transformed_values = pca.fit_transform(clean.values)

    pc_columns = [f"PC{i + 1}" for i in range(n_comp)]
    transformed = pd.DataFrame(transformed_values, index=clean.index, columns=pc_columns)

    # Build loadings DataFrame (factor x PC)
    loadings = pd.DataFrame(pca.components_.T, index=factor_names, columns=pc_columns)

    cumulative_variance = np.cumsum(pca.explained_variance_ratio_).tolist()

    info: dict[str, Any] = {
        "n_components": n_comp,
        "explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
        "loadings": loadings,
        "cumulative_variance": cumulative_variance,
    }

    diag.info(
        src,
        f"PCA: {n_comp} components explain "
        f"{cumulative_variance[-1]:.1%} of variance from {len(factor_names)} factors.",
    )
    return transformed, info, diag


def select_factors_by_pca(
    feature_matrix: pd.DataFrame,
    factor_ic_scores: dict[str, float],
    max_factors: int = 8,
    min_variance_per_factor: float = 0.05,
) -> tuple[list[str], Diagnostics]:
    """Select factors using PCA-informed deduplication.

    Algorithm:
      1. Run PCA, identify principal components
      2. For each PC, find the original factor with highest absolute loading
      3. Rank representative factors by IC
      4. Select top max_factors

    This ensures selected factors span different dimensions of the factor space.

    Parameters
    ----------
    feature_matrix : pd.DataFrame
        Factor matrix (rows x factor columns).
    factor_ic_scores : dict[str, float]
        Mapping of factor_name -> IC mean (used for ranking).
    max_factors : int
        Maximum number of factors to select.
    min_variance_per_factor : float
        Minimum variance ratio a PC must explain to contribute a factor.

    Returns
    -------
    tuple[list[str], Diagnostics]
        (list of selected factor names, diagnostics)
    """
    diag = Diagnostics()
    src = f"{_MOD}.select_factors_by_pca"

    if feature_matrix.empty or feature_matrix.shape[1] == 0:
        diag.warning(src, "Empty feature matrix provided.")
        return [], diag

    if not factor_ic_scores:
        diag.warning(src, "No IC scores provided.")
        return [], diag

    # Run PCA to get all components
    _, info, pca_diag = pca_factor_decomposition(feature_matrix, variance_threshold=0.99)
    diag.merge(pca_diag)

    if info["n_components"] == 0:
        diag.warning(src, "PCA produced 0 components.")
        return [], diag

    loadings: pd.DataFrame = info["loadings"]
    variance_ratios: list[float] = info["explained_variance_ratio"]

    # For each PC, find the factor with the highest absolute loading
    representatives: list[str] = []
    seen: set[str] = set()

    for i, pc_col in enumerate(loadings.columns):
        # Skip PCs that explain too little variance
        if i < len(variance_ratios) and variance_ratios[i] < min_variance_per_factor:
            continue

        abs_loadings = loadings[pc_col].abs()
        # Pick the factor with the highest loading that hasn't been picked yet
        sorted_factors = abs_loadings.sort_values(ascending=False)
        for factor_name in sorted_factors.index:
            if factor_name not in seen and factor_name in factor_ic_scores:
                representatives.append(factor_name)
                seen.add(factor_name)
                break

    # Rank representative factors by absolute IC
    ranked = sorted(representatives, key=lambda f: abs(factor_ic_scores.get(f, 0.0)), reverse=True)

    selected = ranked[:max_factors]

    diag.info(
        src,
        f"PCA-informed selection: {len(selected)} factors from "
        f"{len(representatives)} PC representatives (max={max_factors}).",
    )
    return selected, diag
