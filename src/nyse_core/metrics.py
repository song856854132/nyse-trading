"""Performance metrics — pure leaf computations.

All functions return (result, Diagnostics) tuples per the nyse_core contract.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from nyse_core.contracts import Diagnostics
from nyse_core.schema import TRADING_DAYS_PER_YEAR

_SRC = "metrics"


def sharpe_ratio(returns: pd.Series, annual_factor: int = TRADING_DAYS_PER_YEAR) -> tuple[float, Diagnostics]:
    """Annualized Sharpe ratio (assumes zero risk-free rate).

    Parameters
    ----------
    returns : pd.Series
        Daily arithmetic returns.
    annual_factor : int
        Number of trading days per year.

    Returns
    -------
    tuple[float, Diagnostics]
        (Annualized Sharpe ratio, diagnostics). Returns 0.0 if std is zero.
    """
    diag = Diagnostics()
    r = returns.dropna()
    if len(r) < 2:
        diag.warning(_SRC, "sharpe_ratio: fewer than 2 non-NaN observations", n=len(r))
        return 0.0, diag
    std = r.std(ddof=1)
    if std < 1e-15:
        diag.warning(_SRC, "sharpe_ratio: near-zero std", std=float(std))
        return 0.0, diag
    result = float(r.mean() / std * np.sqrt(annual_factor))
    diag.info(_SRC, "sharpe_ratio computed", value=result, n=len(r))
    return result, diag


def cagr(returns: pd.Series, annual_factor: int = TRADING_DAYS_PER_YEAR) -> tuple[float, Diagnostics]:
    """Compound annual growth rate from daily returns.

    Parameters
    ----------
    returns : pd.Series
        Daily arithmetic returns.
    annual_factor : int
        Number of trading days per year.

    Returns
    -------
    tuple[float, Diagnostics]
        (CAGR as a decimal, diagnostics).
    """
    diag = Diagnostics()
    r = returns.dropna()
    if len(r) == 0:
        diag.warning(_SRC, "cagr: empty returns series")
        return 0.0, diag
    cumulative = (1 + r).prod()
    n_years = len(r) / annual_factor
    if n_years <= 0 or cumulative <= 0:
        diag.warning(
            _SRC,
            "cagr: non-positive cumulative or duration",
            cumulative=float(cumulative),
            n_years=n_years,
        )
        return 0.0, diag
    result = float(cumulative ** (1.0 / n_years) - 1.0)
    diag.info(_SRC, "cagr computed", value=result, n=len(r))
    return result, diag


def max_drawdown(returns: pd.Series) -> tuple[float, Diagnostics]:
    """Maximum drawdown from daily returns.

    Parameters
    ----------
    returns : pd.Series
        Daily arithmetic returns.

    Returns
    -------
    tuple[float, Diagnostics]
        (Maximum drawdown as a negative number, diagnostics).
    """
    diag = Diagnostics()
    r = returns.dropna()
    if len(r) == 0:
        diag.warning(_SRC, "max_drawdown: empty returns series")
        return 0.0, diag
    cumulative = (1 + r).cumprod()
    running_max = cumulative.cummax()
    drawdowns = cumulative / running_max - 1.0
    result = float(drawdowns.min())
    diag.info(_SRC, "max_drawdown computed", value=result, n=len(r))
    return result, diag


def annual_turnover(weights_history: pd.DataFrame) -> tuple[float, Diagnostics]:
    """Annualized portfolio turnover from daily weight snapshots.

    Parameters
    ----------
    weights_history : pd.DataFrame
        Rows = dates, columns = symbols, values = portfolio weights.

    Returns
    -------
    tuple[float, Diagnostics]
        (Annualized one-way turnover, diagnostics).
    """
    diag = Diagnostics()
    if weights_history.shape[0] < 2:
        diag.warning(_SRC, "annual_turnover: fewer than 2 snapshots")
        return 0.0, diag
    daily_changes = weights_history.diff().iloc[1:]
    daily_turnover = daily_changes.abs().sum(axis=1)
    result = float(daily_turnover.mean() * TRADING_DAYS_PER_YEAR)
    diag.info(_SRC, "annual_turnover computed", value=result)
    return result, diag


def information_coefficient(
    factor_scores: pd.Series, forward_returns: pd.Series
) -> tuple[float, Diagnostics]:
    """Spearman rank correlation between factor scores and forward returns.

    Parameters
    ----------
    factor_scores : pd.Series
        Cross-sectional factor scores for one date.
    forward_returns : pd.Series
        Realized forward returns for the same universe.

    Returns
    -------
    tuple[float, Diagnostics]
        (Spearman rank correlation coefficient, diagnostics).
    """
    diag = Diagnostics()
    combined = pd.DataFrame({"score": factor_scores, "ret": forward_returns}).dropna()
    if len(combined) < 3:
        diag.warning(
            _SRC,
            "information_coefficient: fewer than 3 paired observations",
            n=len(combined),
        )
        return 0.0, diag
    corr, _ = sp_stats.spearmanr(combined["score"], combined["ret"])
    result = float(corr)
    diag.info(_SRC, "information_coefficient computed", value=result, n=len(combined))
    return result, diag


def ic_ir(ic_series: pd.Series) -> tuple[float, Diagnostics]:
    """Information ratio of the IC series: mean(IC) / std(IC).

    Parameters
    ----------
    ic_series : pd.Series
        Time series of information coefficients (one IC per rebalance date).

    Returns
    -------
    tuple[float, Diagnostics]
        (IC IR, diagnostics). Returns 0.0 if std is zero or series too short.
    """
    diag = Diagnostics()
    s = ic_series.dropna()
    if len(s) < 2 or s.std(ddof=1) == 0:
        diag.warning(_SRC, "ic_ir: insufficient data or zero std", n=len(s))
        return 0.0, diag
    result = float(s.mean() / s.std(ddof=1))
    diag.info(_SRC, "ic_ir computed", value=result, n=len(s))
    return result, diag


def cost_drag(returns: pd.Series, costs: pd.Series) -> tuple[float, Diagnostics]:
    """Annual cost as percentage of gross returns.

    Parameters
    ----------
    returns : pd.Series
        Gross daily returns (before costs).
    costs : pd.Series
        Daily transaction costs (positive values = costs).

    Returns
    -------
    tuple[float, Diagnostics]
        (Annualized cost drag as a decimal fraction, diagnostics).
    """
    diag = Diagnostics()
    r = returns.dropna()
    c = costs.reindex(r.index).fillna(0.0)
    if len(r) == 0:
        diag.warning(_SRC, "cost_drag: empty returns series")
        return 0.0, diag
    daily_cost_rate = c.mean()
    result = float(daily_cost_rate * TRADING_DAYS_PER_YEAR)
    diag.info(_SRC, "cost_drag computed", value=result, n=len(r))
    return result, diag
