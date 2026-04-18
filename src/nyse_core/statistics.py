"""Statistical tests for factor validation.

Provides permutation tests, block bootstrap confidence intervals, and
Romano-Wolf stepdown multiple-testing correction — all using stationary
block bootstrap to preserve autocorrelation structure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from nyse_core.contracts import Diagnostics
from nyse_core.schema import TRADING_DAYS_PER_YEAR

# ── Helper: circular block bootstrap ────────────────────────────────────────


def _circular_block_resample(data: np.ndarray, block_size: int, rng: np.random.Generator) -> np.ndarray:
    """Resample *data* using circular block bootstrap.

    Blocks wrap around the end of the series to the beginning, preserving
    autocorrelation structure within blocks.
    """
    n = len(data)
    n_blocks = int(np.ceil(n / block_size))
    starts = rng.integers(0, n, size=n_blocks)
    indices = np.concatenate([np.arange(s, s + block_size) % n for s in starts])[:n]
    return data[indices]


def _sharpe(returns: np.ndarray) -> float:
    """Annualized Sharpe ratio from daily returns."""
    if len(returns) == 0 or np.std(returns, ddof=1) == 0:
        return 0.0
    return float(np.mean(returns) / np.std(returns, ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))


# ── Permutation test ────────────────────────────────────────────────────────


def permutation_test(
    returns: pd.Series,
    n_reps: int = 500,
    block_size: int = 63,
) -> tuple[float, Diagnostics]:
    """Stationary block-bootstrap permutation test for Sharpe ratio.

    Tests H0: the strategy Sharpe ratio equals zero. The null distribution
    is built by shuffling returns using circular block bootstrap to preserve
    autocorrelation, then counting how often the permuted Sharpe meets or
    exceeds the observed Sharpe.

    Parameters
    ----------
    returns : pd.Series
        Daily strategy returns (excess or gross).
    n_reps : int
        Number of bootstrap permutations.
    block_size : int
        Average block length for the circular block bootstrap.

    Returns
    -------
    tuple[float, Diagnostics]
        (p_value, diagnostics).
    """
    diag = Diagnostics()
    src = "statistics.permutation_test"

    arr = returns.dropna().values.astype(np.float64)
    if len(arr) < block_size:
        diag.warning(
            src,
            f"Series length ({len(arr)}) < block_size ({block_size}); results may be unreliable.",
        )

    observed_sharpe = _sharpe(arr)
    diag.info(src, f"Observed Sharpe: {observed_sharpe:.4f}")

    rng = np.random.default_rng(42)
    count_ge = 0
    for _ in range(n_reps):
        permuted = _circular_block_resample(arr, block_size, rng)
        # Demean the permuted series to create a null of zero mean
        permuted = permuted - np.mean(permuted) + 0.0
        if _sharpe(permuted) >= observed_sharpe:
            count_ge += 1

    p_value = (count_ge + 1) / (n_reps + 1)  # continuity correction
    diag.info(src, f"Permutation p-value: {p_value:.4f}", n_reps=n_reps)
    return p_value, diag


# ── Block bootstrap CI ──────────────────────────────────────────────────────


def _bootstrap_sharpe_single(arr: np.ndarray, block_size: int, seed: int) -> float:
    """Single bootstrap replicate — designed for joblib parallel dispatch."""
    rng = np.random.default_rng(seed)
    resampled = _circular_block_resample(arr, block_size, rng)
    return _sharpe(resampled)


def block_bootstrap_ci(
    returns: pd.Series,
    n_reps: int = 10000,
    block_size: int = 63,
    alpha: float = 0.05,
) -> tuple[tuple[float, float], Diagnostics]:
    """Block bootstrap confidence interval for the Sharpe ratio.

    Uses circular block bootstrap with joblib parallelism to construct a
    percentile-based CI.

    Parameters
    ----------
    returns : pd.Series
        Daily strategy returns.
    n_reps : int
        Number of bootstrap replicates.
    block_size : int
        Average block length.
    alpha : float
        Significance level (e.g. 0.05 for 95% CI).

    Returns
    -------
    tuple[tuple[float, float], Diagnostics]
        ((lower, upper), diagnostics).
    """
    diag = Diagnostics()
    src = "statistics.block_bootstrap_ci"

    arr = returns.dropna().values.astype(np.float64)
    if len(arr) < 2 * block_size:
        diag.warning(src, "Series shorter than 2x block_size; CI may be wide.")

    rng = np.random.default_rng(42)
    seeds = rng.integers(0, 2**31, size=n_reps)

    sharpe_dist: list[float] = Parallel(n_jobs=-1, backend="loky")(
        delayed(_bootstrap_sharpe_single)(arr, block_size, int(s)) for s in seeds
    )

    lower = float(np.percentile(sharpe_dist, 100 * alpha / 2))
    upper = float(np.percentile(sharpe_dist, 100 * (1 - alpha / 2)))

    diag.info(
        src,
        f"Bootstrap {100 * (1 - alpha):.0f}% CI: [{lower:.4f}, {upper:.4f}]",
        n_reps=n_reps,
    )
    return (lower, upper), diag


# ── Romano-Wolf stepdown ────────────────────────────────────────────────────


def romano_wolf_stepdown(
    factor_returns: dict[str, pd.Series],
    n_reps: int = 500,
) -> tuple[dict[str, float], Diagnostics]:
    """Romano-Wolf stepdown procedure for multiple-testing correction.

    Controls the family-wise error rate when testing multiple factors
    simultaneously, using block bootstrap to preserve time-series structure.

    Parameters
    ----------
    factor_returns : dict[str, pd.Series]
        Mapping of factor name -> daily return series.
    n_reps : int
        Number of bootstrap replicates.

    Returns
    -------
    tuple[dict[str, float], Diagnostics]
        (adjusted_p_values, diagnostics).
    """
    diag = Diagnostics()
    src = "statistics.romano_wolf_stepdown"

    if not factor_returns:
        diag.warning(src, "Empty factor_returns dict.")
        return {}, diag

    names = list(factor_returns.keys())
    block_size = 63

    # Align all series to common index
    aligned = pd.DataFrame(factor_returns).dropna()
    n_obs = len(aligned)
    if n_obs < block_size:
        diag.warning(src, f"Only {n_obs} common observations; results unreliable.")

    data_matrix = aligned.values  # shape (n_obs, n_factors)
    n_factors = data_matrix.shape[1]

    # Observed test statistics (Sharpe ratios)
    observed = np.array([_sharpe(data_matrix[:, j]) for j in range(n_factors)])

    # Generate bootstrap null distribution — full matrix for proper stepdown
    rng = np.random.default_rng(42)
    boot_matrix = np.zeros((n_reps, n_factors))

    for b in range(n_reps):
        # Resample indices (same across all factors to preserve cross-correlation)
        n_blocks = int(np.ceil(n_obs / block_size))
        starts = rng.integers(0, n_obs, size=n_blocks)
        indices = np.concatenate([np.arange(s, s + block_size) % n_obs for s in starts])[:n_obs]
        boot_data = data_matrix[indices]
        # Demean each factor to impose the null
        boot_data = boot_data - boot_data.mean(axis=0)
        boot_matrix[b, :] = np.array([_sharpe(boot_data[:, j]) for j in range(n_factors)])

    # Proper Romano-Wolf stepdown: at each step, compute max statistic
    # over REMAINING (not-yet-processed) hypotheses only
    order = np.argsort(-observed)  # descending
    adjusted_p: dict[str, float] = {}
    prev_p = 0.0
    remaining = set(range(n_factors))

    for idx in order:
        # Max bootstrap statistic over remaining hypotheses
        remaining_cols = sorted(remaining)
        step_max = np.max(boot_matrix[:, remaining_cols], axis=1)
        raw_p = float(np.mean(step_max >= observed[idx]))
        # Enforce monotonicity: adjusted p >= previous adjusted p
        adj_p = max(raw_p, prev_p)
        adjusted_p[names[idx]] = adj_p
        prev_p = adj_p
        remaining.discard(idx)

    diag.info(src, f"Romano-Wolf stepdown on {n_factors} factors", n_reps=n_reps)
    return adjusted_p, diag
