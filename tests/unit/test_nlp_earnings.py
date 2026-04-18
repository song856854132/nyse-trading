"""Tests for nyse_core.features.nlp_earnings — NLP earnings sentiment factors.

Validates:
- Cross-sectional sentiment: multiple symbols -> Series indexed by symbol
- Positive sentiment -> positive score
- Stale data (> 90 days) -> NaN
- Sentiment surprise with improving tone
- Insufficient history -> NaN
- Dispersion for mixed signals
- All NaN -> warning diagnostic
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from nyse_core.contracts import DiagLevel
from nyse_core.features.nlp_earnings import (
    compute_earnings_sentiment,
    compute_sentiment_dispersion,
    compute_sentiment_surprise,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_sentiment_df(
    symbols: list[str],
    scores: list[float],
    dates: list[date] | None = None,
) -> pd.DataFrame:
    """Build a single-observation-per-symbol sentiment DataFrame."""
    if dates is None:
        dates = [date(2024, 12, 15)] * len(symbols)
    return pd.DataFrame(
        {
            "symbol": symbols,
            "date": dates,
            "sentiment_score": scores,
            "sentiment_std": [0.2] * len(symbols),
            "n_sentences": [100] * len(symbols),
        }
    )


def _make_multi_quarter_df(
    symbol: str,
    scores: list[float],
    start_date: date = date(2023, 4, 15),
) -> pd.DataFrame:
    """Build a multi-quarter sentiment DataFrame for one symbol."""
    records = []
    for i, score in enumerate(scores):
        d = start_date + timedelta(days=91 * i)
        records.append(
            {
                "symbol": symbol,
                "date": d,
                "sentiment_score": score,
                "sentiment_std": 0.2,
                "n_sentences": 100,
            }
        )
    return pd.DataFrame(records)


# ── compute_earnings_sentiment ──────────────────────────────────────────────


class TestEarningsSentimentCrossSectional:
    """Multiple symbols -> Series indexed by symbol."""

    def test_sentiment_cross_sectional(self) -> None:
        """Multiple symbols produce a Series indexed by symbol."""
        symbols = ["AAPL", "MSFT", "GOOG", "AMZN"]
        scores = [0.3, -0.1, 0.5, 0.0]
        df = _make_sentiment_df(symbols, scores)

        series, diag = compute_earnings_sentiment(df)

        assert len(series) == 4
        assert series.index.name == "symbol"
        assert set(series.index) == set(symbols)
        assert not diag.has_errors

    def test_positive_sentiment_positive_score(self) -> None:
        """Stock with sentiment=0.5 produces a positive score."""
        df = _make_sentiment_df(["AAPL"], [0.5])
        series, diag = compute_earnings_sentiment(df)

        assert series["AAPL"] == pytest.approx(0.5)
        assert series["AAPL"] > 0

    def test_negative_sentiment_negative_score(self) -> None:
        """Stock with sentiment=-0.3 produces a negative score."""
        df = _make_sentiment_df(["AAPL"], [-0.3])
        series, diag = compute_earnings_sentiment(df)

        assert series["AAPL"] == pytest.approx(-0.3)
        assert series["AAPL"] < 0


class TestEarningsSentimentRecency:
    """Stale data (> 90 days old) -> NaN."""

    def test_no_recent_sentiment_returns_nan(self) -> None:
        """Sentiment older than 90 days produces NaN."""
        old_date = date(2024, 1, 1)  # much older than reference
        df = _make_sentiment_df(["AAPL"], [0.5], dates=[old_date])

        reference = date(2024, 12, 15)
        series, diag = compute_earnings_sentiment(df, reference_date=reference)

        assert np.isnan(series["AAPL"])
        assert diag.has_warnings

    def test_recent_sentiment_not_nan(self) -> None:
        """Sentiment within 90 days is not NaN."""
        recent_date = date(2024, 12, 1)
        df = _make_sentiment_df(["AAPL"], [0.3], dates=[recent_date])

        reference = date(2024, 12, 15)
        series, diag = compute_earnings_sentiment(df, reference_date=reference)

        assert not np.isnan(series["AAPL"])
        assert series["AAPL"] == pytest.approx(0.3)

    def test_mixed_recency(self) -> None:
        """Mix of recent and stale: stale -> NaN, recent -> value."""
        df = pd.DataFrame(
            {
                "symbol": ["AAPL", "MSFT"],
                "date": [date(2024, 12, 1), date(2024, 1, 1)],
                "sentiment_score": [0.3, 0.5],
                "sentiment_std": [0.2, 0.2],
                "n_sentences": [100, 100],
            }
        )
        reference = date(2024, 12, 15)
        series, diag = compute_earnings_sentiment(df, reference_date=reference)

        assert not np.isnan(series["AAPL"])
        assert np.isnan(series["MSFT"])


class TestAllNanWarning:
    """All NaN should produce a warning diagnostic."""

    def test_all_nan_produces_warning_diagnostic(self) -> None:
        """When all symbols produce NaN, a warning is emitted."""
        old_dates = [date(2024, 1, 1), date(2024, 1, 2)]
        df = _make_sentiment_df(["AAPL", "MSFT"], [0.5, 0.3], dates=old_dates)

        reference = date(2024, 12, 15)
        series, diag = compute_earnings_sentiment(df, reference_date=reference)

        assert series.isna().all()
        warning_messages = [m for m in diag.messages if m.level == DiagLevel.WARNING]
        all_nan_warnings = [m for m in warning_messages if "All symbols produced NaN" in m.message]
        assert len(all_nan_warnings) >= 1

    def test_empty_dataframe_warning(self) -> None:
        """Empty DataFrame produces warning diagnostic."""
        df = pd.DataFrame(columns=["symbol", "date", "sentiment_score"])
        series, diag = compute_earnings_sentiment(df)

        assert len(series) == 0
        assert diag.has_warnings


# ── compute_sentiment_surprise ──────────────────────────────────────────────


class TestSentimentSurprise:
    """Sentiment surprise = current - rolling 4-quarter mean."""

    def test_sentiment_surprise_improving(self) -> None:
        """4 quarters at ~0.1 then jump to 0.5 -> positive surprise."""
        # 5 quarters: 4 prior at 0.1, current at 0.5
        scores = [0.1, 0.1, 0.1, 0.1, 0.5]
        df = _make_multi_quarter_df("AAPL", scores)

        series, diag = compute_sentiment_surprise(df)

        # surprise = 0.5 - mean([0.1, 0.1, 0.1, 0.1]) = 0.5 - 0.1 = 0.4
        assert series["AAPL"] == pytest.approx(0.4, abs=1e-6)
        assert series["AAPL"] > 0  # positive surprise

    def test_sentiment_surprise_deteriorating(self) -> None:
        """4 quarters at 0.5 then drop to -0.1 -> negative surprise."""
        scores = [0.5, 0.5, 0.5, 0.5, -0.1]
        df = _make_multi_quarter_df("AAPL", scores)

        series, diag = compute_sentiment_surprise(df)

        # surprise = -0.1 - mean([0.5, 0.5, 0.5, 0.5]) = -0.1 - 0.5 = -0.6
        assert series["AAPL"] == pytest.approx(-0.6, abs=1e-6)
        assert series["AAPL"] < 0  # negative surprise

    def test_sentiment_surprise_insufficient_history(self) -> None:
        """< 5 quarters (4 for rolling + 1 current) -> NaN."""
        # Only 3 quarters
        scores = [0.1, 0.2, 0.3]
        df = _make_multi_quarter_df("AAPL", scores)

        series, diag = compute_sentiment_surprise(df)

        assert np.isnan(series["AAPL"])
        assert diag.has_warnings

    def test_sentiment_surprise_cross_sectional(self) -> None:
        """Multiple symbols: one improving, one insufficient history."""
        df_improving = _make_multi_quarter_df("AAPL", [0.1, 0.1, 0.1, 0.1, 0.5])
        df_short = _make_multi_quarter_df("MSFT", [0.2, 0.3])
        df = pd.concat([df_improving, df_short], ignore_index=True)

        series, diag = compute_sentiment_surprise(df)

        assert len(series) == 2
        assert not np.isnan(series["AAPL"])
        assert np.isnan(series["MSFT"])


# ── compute_sentiment_dispersion ────────────────────────────────────────────


class TestSentimentDispersion:
    """Within-transcript sentiment dispersion."""

    def test_dispersion_high_for_mixed_signals(self) -> None:
        """sentiment_std=0.7 -> high dispersion value."""
        df = pd.DataFrame(
            {
                "symbol": ["AAPL"],
                "date": [date(2024, 12, 1)],
                "sentiment_std": [0.7],
            }
        )
        reference = date(2024, 12, 15)
        series, diag = compute_sentiment_dispersion(df, reference_date=reference)

        assert series["AAPL"] == pytest.approx(0.7)
        assert series["AAPL"] > 0.5  # high dispersion

    def test_dispersion_low_for_consistent_signals(self) -> None:
        """sentiment_std=0.1 -> low dispersion value."""
        df = pd.DataFrame(
            {
                "symbol": ["AAPL"],
                "date": [date(2024, 12, 1)],
                "sentiment_std": [0.1],
            }
        )
        reference = date(2024, 12, 15)
        series, diag = compute_sentiment_dispersion(df, reference_date=reference)

        assert series["AAPL"] == pytest.approx(0.1)
        assert series["AAPL"] < 0.3  # low dispersion

    def test_dispersion_stale_returns_nan(self) -> None:
        """Dispersion data older than 90 days -> NaN."""
        df = pd.DataFrame(
            {
                "symbol": ["AAPL"],
                "date": [date(2024, 1, 1)],
                "sentiment_std": [0.5],
            }
        )
        reference = date(2024, 12, 15)
        series, diag = compute_sentiment_dispersion(df, reference_date=reference)

        assert np.isnan(series["AAPL"])

    def test_dispersion_missing_std_returns_nan(self) -> None:
        """Missing sentiment_std -> NaN."""
        df = pd.DataFrame(
            {
                "symbol": ["AAPL"],
                "date": [date(2024, 12, 1)],
                "sentiment_std": [np.nan],
            }
        )
        reference = date(2024, 12, 15)
        series, diag = compute_sentiment_dispersion(df, reference_date=reference)

        assert np.isnan(series["AAPL"])

    def test_dispersion_cross_sectional(self) -> None:
        """Multiple symbols each get their own dispersion value."""
        df = pd.DataFrame(
            {
                "symbol": ["AAPL", "MSFT", "GOOG"],
                "date": [date(2024, 12, 1)] * 3,
                "sentiment_std": [0.1, 0.5, 0.7],
            }
        )
        reference = date(2024, 12, 15)
        series, diag = compute_sentiment_dispersion(df, reference_date=reference)

        assert len(series) == 3
        assert series["AAPL"] < series["MSFT"] < series["GOOG"]
