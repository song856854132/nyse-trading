"""NLP earnings sentiment factor computations — pre-computed transcript signals.

Accepts DataFrames with pre-computed sentiment scores from the transcript
adapter (nyse_ats.data.transcript_adapter) and returns cross-sectional
factor values.

All functions are PURE: no I/O, no model loading, no logging.
The transcript adapter handles all inference and data fetching.

Three factors:
  1. earnings_sentiment — most recent sentiment score per symbol
  2. sentiment_surprise — change vs. rolling 4-quarter mean
  3. sentiment_dispersion — within-transcript sentence-level std

Sign conventions are documented but NOT applied here — the FactorRegistry
handles inversion.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_DATE, COL_SYMBOL

# ── Column Names (transcript sentiment data) ─────────────────────────────────
COL_SENTIMENT_SCORE: str = "sentiment_score"
COL_SENTIMENT_STD: str = "sentiment_std"
COL_N_SENTENCES: str = "n_sentences"

# ── Constants ─────────────────────────────────────────────────────────────────
_RECENCY_DAYS: int = 90
_MIN_QUARTERS_FOR_SURPRISE: int = 4


def compute_earnings_sentiment(
    data: pd.DataFrame,
    reference_date: date | None = None,
) -> tuple[pd.Series, Diagnostics]:
    """Most recent earnings call sentiment per symbol.

    Cross-sectional: accepts multi-stock DataFrame, returns one value per symbol.
    Takes the MOST RECENT sentiment_score within the last 90 days from
    reference_date (defaults to the max date in the data).

    Sign convention: POSITIVE (+1). Positive sentiment = buy signal.

    Handles:
      - No recent sentiment (> 90 days old) -> NaN for that symbol.
      - All NaN -> WARNING diagnostic.

    Parameters
    ----------
    data : pd.DataFrame
        Columns: symbol, date, sentiment_score (float, -1 to +1).
    reference_date : date | None
        Cutoff date for recency; defaults to max(date) in data.

    Returns
    -------
    (pd.Series indexed by symbol, Diagnostics)
    """
    diag = Diagnostics()
    source = "nlp_earnings.compute_earnings_sentiment"

    required_cols = {COL_SYMBOL, COL_DATE, COL_SENTIMENT_SCORE}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        diag.error(source, f"Missing required columns: {missing_cols}")
        return pd.Series(dtype=float, name="earnings_sentiment"), diag

    if data.empty:
        diag.warning(source, "Input DataFrame is empty; all symbols will be NaN.")
        return pd.Series(dtype=float, name="earnings_sentiment"), diag

    # Ensure date column is date type for comparison
    dates = pd.to_datetime(data[COL_DATE]).dt.date
    if reference_date is None:
        reference_date = max(dates)

    cutoff = reference_date - timedelta(days=_RECENCY_DAYS)

    results: dict[str, float] = {}
    stale_count = 0

    for symbol, group in data.groupby(COL_SYMBOL):
        group_dates = pd.to_datetime(group[COL_DATE]).dt.date
        recent_mask = group_dates >= cutoff
        recent = group.loc[recent_mask]

        if recent.empty:
            results[symbol] = np.nan
            stale_count += 1
            continue

        # Take the most recent observation
        latest_idx = pd.to_datetime(recent[COL_DATE]).idxmax()
        score = recent.loc[latest_idx, COL_SENTIMENT_SCORE]

        if pd.isna(score):
            results[symbol] = np.nan
            stale_count += 1
        else:
            results[symbol] = float(score)

    if stale_count > 0:
        diag.warning(
            source,
            f"{stale_count} symbol(s) had no recent sentiment (within {_RECENCY_DAYS} days); set to NaN.",
            stale_count=stale_count,
            recency_days=_RECENCY_DAYS,
        )

    series = pd.Series(results, name="earnings_sentiment")
    series.index.name = COL_SYMBOL

    all_nan = series.isna().all() if len(series) > 0 else True
    if all_nan:
        diag.warning(
            source,
            "All symbols produced NaN sentiment scores.",
        )

    n_valid = int((~series.isna()).sum()) if len(series) > 0 else 0
    diag.info(
        source,
        "Cross-sectional earnings sentiment computed.",
        n_symbols=len(results),
        n_valid=n_valid,
        reference_date=str(reference_date),
    )
    return series, diag


def compute_sentiment_surprise(
    data: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Sentiment surprise: current sentiment minus rolling 4-quarter mean.

    Captures CHANGE in management tone, not absolute level. Improving tone
    is a stronger signal than consistently positive tone.

    Cross-sectional: accepts multi-stock DataFrame, returns one value per symbol.
    Requires >= 4 quarters of history per symbol.

    Sign convention: POSITIVE (+1). Improving sentiment = buy signal.

    Handles:
      - Insufficient history (< 4 quarters) -> NaN.
      - All NaN -> WARNING diagnostic.

    Parameters
    ----------
    data : pd.DataFrame
        Columns: symbol, date, sentiment_score.
        Multiple rows per symbol (one per earnings call / quarter).

    Returns
    -------
    (pd.Series indexed by symbol, Diagnostics)
    """
    diag = Diagnostics()
    source = "nlp_earnings.compute_sentiment_surprise"

    required_cols = {COL_SYMBOL, COL_DATE, COL_SENTIMENT_SCORE}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        diag.error(source, f"Missing required columns: {missing_cols}")
        return pd.Series(dtype=float, name="sentiment_surprise"), diag

    if data.empty:
        diag.warning(source, "Input DataFrame is empty; all symbols will be NaN.")
        return pd.Series(dtype=float, name="sentiment_surprise"), diag

    results: dict[str, float] = {}
    insufficient_count = 0

    for symbol, group in data.groupby(COL_SYMBOL):
        group_sorted = group.sort_values(COL_DATE)
        scores = group_sorted[COL_SENTIMENT_SCORE].dropna().values

        if len(scores) < _MIN_QUARTERS_FOR_SURPRISE + 1:
            # Need at least 5 data points: 4 for rolling mean + 1 current
            results[symbol] = np.nan
            insufficient_count += 1
            continue

        current = scores[-1]
        # Rolling mean of the previous 4 quarters (excluding current)
        prior_mean = float(np.mean(scores[-5:-1]))
        surprise = float(current - prior_mean)
        results[symbol] = surprise

    if insufficient_count > 0:
        diag.warning(
            source,
            f"{insufficient_count} symbol(s) had insufficient history "
            f"(< {_MIN_QUARTERS_FOR_SURPRISE + 1} quarters) for sentiment "
            f"surprise; set to NaN.",
            insufficient_count=insufficient_count,
            min_required=_MIN_QUARTERS_FOR_SURPRISE + 1,
        )

    series = pd.Series(results, name="sentiment_surprise")
    series.index.name = COL_SYMBOL

    all_nan = series.isna().all() if len(series) > 0 else True
    if all_nan:
        diag.warning(
            source,
            "All symbols produced NaN sentiment surprise scores.",
        )

    n_valid = int((~series.isna()).sum()) if len(series) > 0 else 0
    diag.info(
        source,
        "Cross-sectional sentiment surprise computed.",
        n_symbols=len(results),
        n_valid=n_valid,
    )
    return series, diag


def compute_sentiment_dispersion(
    data: pd.DataFrame,
    reference_date: date | None = None,
) -> tuple[pd.Series, Diagnostics]:
    """Sentence-level sentiment dispersion within the most recent transcript.

    High dispersion (high std of sentence-level sentiments) indicates mixed
    signals in management's tone — associated with future negative returns.

    Cross-sectional: accepts multi-stock DataFrame, returns one value per symbol.
    Uses the MOST RECENT sentiment_std within the last 90 days.

    Sign convention: NEGATIVE (-1). High dispersion = mixed signals = bearish.
    Registry will negate so higher = buy.

    Handles:
      - Missing sentiment_std -> NaN.
      - No recent data (> 90 days old) -> NaN.
      - All NaN -> WARNING diagnostic.

    Parameters
    ----------
    data : pd.DataFrame
        Columns: symbol, date, sentiment_std (pre-computed by adapter).
    reference_date : date | None
        Cutoff date for recency; defaults to max(date) in data.

    Returns
    -------
    (pd.Series indexed by symbol, Diagnostics)
    """
    diag = Diagnostics()
    source = "nlp_earnings.compute_sentiment_dispersion"

    required_cols = {COL_SYMBOL, COL_DATE, COL_SENTIMENT_STD}
    missing_cols = required_cols - set(data.columns)
    if missing_cols:
        diag.error(source, f"Missing required columns: {missing_cols}")
        return pd.Series(dtype=float, name="sentiment_dispersion"), diag

    if data.empty:
        diag.warning(source, "Input DataFrame is empty; all symbols will be NaN.")
        return pd.Series(dtype=float, name="sentiment_dispersion"), diag

    dates = pd.to_datetime(data[COL_DATE]).dt.date
    if reference_date is None:
        reference_date = max(dates)

    cutoff = reference_date - timedelta(days=_RECENCY_DAYS)

    results: dict[str, float] = {}
    missing_count = 0

    for symbol, group in data.groupby(COL_SYMBOL):
        group_dates = pd.to_datetime(group[COL_DATE]).dt.date
        recent_mask = group_dates >= cutoff
        recent = group.loc[recent_mask]

        if recent.empty:
            results[symbol] = np.nan
            missing_count += 1
            continue

        # Take the most recent observation
        latest_idx = pd.to_datetime(recent[COL_DATE]).idxmax()
        std_val = recent.loc[latest_idx, COL_SENTIMENT_STD]

        if pd.isna(std_val):
            results[symbol] = np.nan
            missing_count += 1
        else:
            results[symbol] = float(std_val)

    if missing_count > 0:
        diag.warning(
            source,
            f"{missing_count} symbol(s) had no recent sentiment dispersion data; set to NaN.",
            missing_count=missing_count,
        )

    series = pd.Series(results, name="sentiment_dispersion")
    series.index.name = COL_SYMBOL

    all_nan = series.isna().all() if len(series) > 0 else True
    if all_nan:
        diag.warning(
            source,
            "All symbols produced NaN sentiment dispersion scores.",
        )

    n_valid = int((~series.isna()).sum()) if len(series) > 0 else 0
    diag.info(
        source,
        "Cross-sectional sentiment dispersion computed.",
        n_symbols=len(results),
        n_valid=n_valid,
    )
    return series, diag
