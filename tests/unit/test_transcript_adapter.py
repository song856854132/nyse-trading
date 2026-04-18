"""Tests for nyse_ats.data.transcript_adapter — earnings transcript sentiment.

Validates:
- Dictionary mode: positive text -> positive score
- Dictionary mode: negative text -> negative score
- Dictionary mode: neutral text -> near-zero score
- FinBERT fallback to dictionary when transformers not installed
- fetch() returns expected columns
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from nyse_ats.data.transcript_adapter import (
    LM_NEGATIVE_WORDS,
    LM_POSITIVE_WORDS,
    TranscriptAdapter,
)
from nyse_core.contracts import DiagLevel

# ── Dictionary Mode Scoring ─────────────────────────────────────────────────


class TestDictionaryModePositive:
    """Positive financial text -> positive sentiment score."""

    def test_dictionary_mode_scores_positive_text(self) -> None:
        adapter = TranscriptAdapter(scoring_mode="dictionary")

        text = (
            "We achieved strong growth this quarter. "
            "Revenue exceeded expectations and profitability improved significantly. "
            "Our robust performance reflects the strength of our business model. "
            "We are confident in our favorable outlook and expect continued success."
        )

        score, std, n_sentences = adapter.score_text_dictionary(text)

        assert score > 0, f"Expected positive score, got {score}"
        assert n_sentences >= 3
        assert std >= 0

    def test_highly_positive_text(self) -> None:
        adapter = TranscriptAdapter(scoring_mode="dictionary")

        text = (
            "Exceptional growth delivered outstanding results. "
            "We achieved record profitable performance. "
            "Strong improvement enabled remarkable success. "
            "Excellent opportunities for sustainable advancement."
        )

        score, _, _ = adapter.score_text_dictionary(text)
        assert score > 0


class TestDictionaryModeNegative:
    """Negative financial text -> negative sentiment score."""

    def test_dictionary_mode_scores_negative_text(self) -> None:
        adapter = TranscriptAdapter(scoring_mode="dictionary")

        text = (
            "We suffered significant losses this quarter. "
            "Revenue declined sharply amid deteriorating market conditions. "
            "The lawsuit and litigation costs weakened our financial position. "
            "Risk of further decline remains a serious concern."
        )

        score, std, n_sentences = adapter.score_text_dictionary(text)

        assert score < 0, f"Expected negative score, got {score}"
        assert n_sentences >= 3
        assert std >= 0

    def test_highly_negative_text(self) -> None:
        adapter = TranscriptAdapter(scoring_mode="dictionary")

        text = (
            "Severe losses resulted in bankruptcy risk. "
            "Failure to address deteriorating conditions led to crisis. "
            "Litigation and penalty costs worsened the deficit. "
            "Weak performance amid recession and decline."
        )

        score, _, _ = adapter.score_text_dictionary(text)
        assert score < 0


class TestDictionaryModeNeutral:
    """Balanced text -> near-zero sentiment score."""

    def test_dictionary_mode_neutral_text(self) -> None:
        adapter = TranscriptAdapter(scoring_mode="dictionary")

        text = (
            "The company reported its quarterly results today. "
            "Management discussed operations and strategy for the next period. "
            "The board reviewed the annual report and financial statements. "
            "Analysts asked questions about market conditions and competition."
        )

        score, _, n_sentences = adapter.score_text_dictionary(text)

        assert abs(score) < 0.15, f"Expected near-zero score, got {score}"
        assert n_sentences >= 3


# ── Dictionary Word Lists ────────────────────────────────────────────────────


class TestDictionaryWordLists:
    """Loughran-McDonald word lists have minimum sizes."""

    def test_positive_words_minimum_count(self) -> None:
        """At least 50 positive words in the dictionary."""
        assert len(LM_POSITIVE_WORDS) >= 50

    def test_negative_words_minimum_count(self) -> None:
        """At least 100 negative words in the dictionary."""
        assert len(LM_NEGATIVE_WORDS) >= 100

    def test_no_overlap(self) -> None:
        """Positive and negative word sets should not overlap."""
        overlap = LM_POSITIVE_WORDS & LM_NEGATIVE_WORDS
        assert len(overlap) == 0, f"Overlapping words: {overlap}"

    def test_all_lowercase(self) -> None:
        """All dictionary words should be lowercase."""
        for word in LM_POSITIVE_WORDS:
            assert word == word.lower(), f"Positive word not lowercase: {word}"
        for word in LM_NEGATIVE_WORDS:
            assert word == word.lower(), f"Negative word not lowercase: {word}"


# ── FinBERT Fallback ─────────────────────────────────────────────────────────


class TestFinBERTFallback:
    """When transformers is not installed, FinBERT mode falls back to dictionary."""

    def test_finbert_fallback_to_dictionary(self) -> None:
        """When transformers import fails, adapter uses dictionary + warning."""
        with patch.dict("sys.modules", {"transformers": None}):
            adapter = TranscriptAdapter(scoring_mode="finbert")

        assert adapter.effective_mode == "dictionary"

    def test_dictionary_mode_explicit(self) -> None:
        """Explicit dictionary mode works without any fallback."""
        adapter = TranscriptAdapter(scoring_mode="dictionary")
        assert adapter.effective_mode == "dictionary"

    def test_invalid_mode_raises(self) -> None:
        """Invalid scoring mode raises ValueError."""
        with pytest.raises(ValueError, match="scoring_mode must be"):
            TranscriptAdapter(scoring_mode="invalid")


# ── Fetch Schema ─────────────────────────────────────────────────────────────


class TestFetchSchema:
    """fetch() returns expected columns and diagnostics."""

    def test_fetch_returns_expected_columns(self) -> None:
        """Returned DataFrame has the correct column schema."""
        adapter = TranscriptAdapter(scoring_mode="dictionary")
        df, diag = adapter.fetch(
            symbols=["AAPL", "MSFT"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        expected_cols = {"symbol", "date", "sentiment_score", "sentiment_std", "n_sentences"}
        assert set(df.columns) == expected_cols

    def test_fetch_warns_about_stub(self) -> None:
        """fetch() warns that transcript source is not configured."""
        adapter = TranscriptAdapter(scoring_mode="dictionary")
        df, diag = adapter.fetch(
            symbols=["AAPL"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert diag.has_warnings
        warning_messages = [m for m in diag.messages if m.level == DiagLevel.WARNING]
        stub_warnings = [m for m in warning_messages if "not configured" in m.message]
        assert len(stub_warnings) >= 1

    def test_fetch_returns_empty_dataframe(self) -> None:
        """fetch() returns empty DataFrame (stub implementation)."""
        adapter = TranscriptAdapter(scoring_mode="dictionary")
        df, _ = adapter.fetch(
            symbols=["AAPL"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert len(df) == 0


# ── Score Text Integration ──────────────────────────────────────────────────


class TestScoreText:
    """score_text dispatches to the correct backend."""

    def test_score_text_dictionary_dispatch(self) -> None:
        """score_text uses dictionary mode when configured."""
        adapter = TranscriptAdapter(scoring_mode="dictionary")
        score, std, n = adapter.score_text("Strong growth and profitable results exceeded expectations.")
        assert score > 0
        assert n >= 1

    def test_score_text_empty_string(self) -> None:
        """Empty text returns zero score."""
        adapter = TranscriptAdapter(scoring_mode="dictionary")
        score, std, n = adapter.score_text("")
        assert score == 0.0
        assert n == 0

    def test_sentence_level_std(self) -> None:
        """Mixed text with positive and negative sentences has nonzero std."""
        adapter = TranscriptAdapter(scoring_mode="dictionary")
        text = (
            "We achieved exceptional growth and record profits this quarter. "
            "However we suffered severe losses in the international division. "
            "Strong improvement in domestic markets offset the decline abroad."
        )
        score, std, n = adapter.score_text_dictionary(text)
        assert n >= 2
        # Std should be nonzero for mixed text
        assert std > 0
