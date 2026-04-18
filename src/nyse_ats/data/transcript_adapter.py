"""Transcript adapter — fetches earnings call transcripts and computes sentiment.

Two scoring modes:
  - 'dictionary': Loughran-McDonald financial sentiment dictionary (fast, no model)
  - 'finbert': HuggingFace FinBERT model (higher quality, requires GPU/CPU inference)

The adapter returns a DataFrame ready for nyse_core/features/nlp_earnings.py:
  columns: symbol, date, sentiment_score, sentiment_std, n_sentences

ARCHITECTURE: This lives in nyse_ats (I/O layer). It may import os, logging,
requests, transformers, etc.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_DATE, COL_SYMBOL

if TYPE_CHECKING:
    from datetime import date

    from nyse_ats.data.rate_limiter import SlidingWindowRateLimiter

logger = logging.getLogger(__name__)

_SRC = "transcript_adapter"

# ── Output Column Names ─────────────────────────────────────────────────────
COL_SENTIMENT_SCORE = "sentiment_score"
COL_SENTIMENT_STD = "sentiment_std"
COL_N_SENTENCES = "n_sentences"

_OUTPUT_COLS = [COL_SYMBOL, COL_DATE, COL_SENTIMENT_SCORE, COL_SENTIMENT_STD, COL_N_SENTENCES]

# ── Loughran-McDonald Financial Sentiment Dictionary ────────────────────────
# Subset of the full LM dictionary — words commonly occurring in earnings calls.
# Full dictionary: ~354 positive, ~2,355 negative (Loughran & McDonald, 2011).

LM_POSITIVE_WORDS: frozenset[str] = frozenset(
    {
        "accomplish",
        "accomplished",
        "achieve",
        "achieved",
        "achievement",
        "advance",
        "advanced",
        "advancement",
        "advantage",
        "beneficial",
        "benefit",
        "benefited",
        "best",
        "better",
        "boost",
        "boosted",
        "breakthrough",
        "collaborate",
        "compliment",
        "confidence",
        "confident",
        "constructive",
        "creative",
        "deliver",
        "delivered",
        "dependable",
        "desirable",
        "diligent",
        "distinction",
        "efficient",
        "enable",
        "enabled",
        "enhance",
        "enhanced",
        "enhancement",
        "enjoy",
        "enjoyed",
        "excellent",
        "exceed",
        "exceeded",
        "exceptional",
        "exciting",
        "exclusive",
        "expand",
        "expanded",
        "expansion",
        "favorable",
        "gain",
        "gained",
        "generous",
        "great",
        "greatest",
        "grew",
        "grow",
        "growing",
        "growth",
        "highest",
        "improve",
        "improved",
        "improvement",
        "impressive",
        "increase",
        "increased",
        "incredible",
        "innovation",
        "innovative",
        "leader",
        "leadership",
        "lucrative",
        "maximize",
        "notable",
        "opportunities",
        "opportunity",
        "optimal",
        "optimistic",
        "outperform",
        "outperformed",
        "outstanding",
        "overcome",
        "pleased",
        "positive",
        "profitable",
        "profitability",
        "profit",
        "progress",
        "progression",
        "promise",
        "promising",
        "prosperous",
        "rebound",
        "rebounded",
        "record",
        "recover",
        "recovered",
        "recovery",
        "reliable",
        "remarkable",
        "resolve",
        "resolved",
        "resilient",
        "reward",
        "rewarding",
        "robust",
        "satisfaction",
        "smooth",
        "solid",
        "solution",
        "solved",
        "spectacular",
        "stability",
        "stabilize",
        "stable",
        "strength",
        "strengthen",
        "strengthened",
        "strong",
        "stronger",
        "strongest",
        "succeed",
        "succeeded",
        "success",
        "successful",
        "superior",
        "surpass",
        "surpassed",
        "sustain",
        "sustainable",
        "tremendous",
        "upturn",
        "upward",
        "valuable",
        "winner",
        "winning",
    }
)

LM_NEGATIVE_WORDS: frozenset[str] = frozenset(
    {
        "abandon",
        "abandoned",
        "abnormal",
        "abuse",
        "accident",
        "adverse",
        "adversely",
        "allegation",
        "allegations",
        "amortize",
        "annul",
        "antitrust",
        "argue",
        "arrearage",
        "arrearages",
        "attrition",
        "bad",
        "bankrupt",
        "bankruptcy",
        "bottleneck",
        "breach",
        "burden",
        "burdensome",
        "catastrophe",
        "caution",
        "cautionary",
        "cease",
        "challenge",
        "challenged",
        "challenges",
        "claim",
        "claims",
        "closure",
        "closures",
        "collapse",
        "collapsed",
        "complaint",
        "complaints",
        "concern",
        "concerned",
        "concerns",
        "condemn",
        "conflict",
        "constraint",
        "constraints",
        "contraction",
        "costly",
        "crisis",
        "critical",
        "criticize",
        "curtail",
        "curtailed",
        "damage",
        "damaged",
        "damages",
        "danger",
        "dangerous",
        "deadlock",
        "debt",
        "decline",
        "declined",
        "declining",
        "decrease",
        "decreased",
        "default",
        "defaults",
        "defect",
        "defective",
        "deficiency",
        "deficit",
        "deficits",
        "degradation",
        "delay",
        "delayed",
        "delays",
        "delinquency",
        "delinquent",
        "demolish",
        "denial",
        "deplete",
        "depleted",
        "depletion",
        "depreciation",
        "depressed",
        "depression",
        "destabilize",
        "deteriorate",
        "deteriorated",
        "deteriorating",
        "deterioration",
        "detrimental",
        "devalue",
        "difficulty",
        "diminish",
        "diminished",
        "disadvantage",
        "disappoint",
        "disappointed",
        "disappointing",
        "disappointment",
        "disaster",
        "disclaim",
        "discontinue",
        "discontinued",
        "discrepancy",
        "dismal",
        "dismiss",
        "dismissal",
        "disruption",
        "disruptions",
        "dissatisfaction",
        "dissolution",
        "distress",
        "divest",
        "divestiture",
        "doubt",
        "doubtful",
        "downgrade",
        "downgraded",
        "downturn",
        "drag",
        "drastically",
        "drop",
        "dropped",
        "encumber",
        "erode",
        "eroded",
        "erosion",
        "error",
        "errors",
        "eviction",
        "exacerbate",
        "excessive",
        "exhaust",
        "exhausted",
        "expense",
        "expenses",
        "expose",
        "exposure",
        "fail",
        "failed",
        "failing",
        "failure",
        "failures",
        "fall",
        "fallen",
        "falling",
        "felony",
        "fine",
        "fined",
        "fines",
        "fire",
        "fired",
        "fluctuate",
        "fluctuation",
        "force",
        "forced",
        "foreclose",
        "foreclosure",
        "forfeit",
        "forfeiture",
        "fraud",
        "fraudulent",
        "halt",
        "halted",
        "hamper",
        "hampered",
        "hardship",
        "harm",
        "harmful",
        "hinder",
        "hindered",
        "hostile",
        "hurdle",
        "idle",
        "illegal",
        "impair",
        "impaired",
        "impairment",
        "impediment",
        "inability",
        "inadequacy",
        "inadequate",
        "incapable",
        "incompatible",
        "inconvenience",
        "indebtedness",
        "indictment",
        "ineffective",
        "inefficiency",
        "inferior",
        "inflation",
        "inflationary",
        "infringe",
        "infringement",
        "injunction",
        "insolvency",
        "insolvent",
        "insufficient",
        "interrupt",
        "interruption",
        "investigation",
        "jeopardize",
        "lack",
        "lacked",
        "lacking",
        "lag",
        "lagged",
        "lagging",
        "lapse",
        "late",
        "lawsuit",
        "lawsuits",
        "layoff",
        "layoffs",
        "liability",
        "liabilities",
        "lien",
        "liens",
        "liquidate",
        "liquidation",
        "litigation",
        "lose",
        "loss",
        "losses",
        "lost",
        "low",
        "lower",
        "lowest",
        "malfunction",
        "mandatory",
        "misappropriate",
        "misconduct",
        "mismanage",
        "misrepresent",
        "misrepresentation",
        "miss",
        "missed",
        "mistake",
        "monopoly",
        "moratorium",
        "negative",
        "negatively",
        "neglect",
        "negligence",
        "negligent",
        "noncompliance",
        "nonpayment",
        "nonperformance",
        "obstacle",
        "obsolete",
        "obsolescence",
        "offense",
        "omission",
        "onerous",
        "oppose",
        "opposition",
        "outage",
        "overburden",
        "overdue",
        "overload",
        "overrun",
        "oversupply",
        "penalty",
        "penalties",
        "peril",
        "persist",
        "plaintiff",
        "plummet",
        "poor",
        "poorly",
        "postpone",
        "postponed",
        "precipitous",
        "preclude",
        "prejudice",
        "pressure",
        "pressured",
        "problem",
        "problematic",
        "problems",
        "prosecute",
        "protest",
        "punish",
        "punitive",
        "questionable",
        "recall",
        "recalls",
        "recession",
        "recessionary",
        "reclaim",
        "reduce",
        "reduced",
        "reduction",
        "redundancy",
        "reimburse",
        "reject",
        "rejected",
        "rejection",
        "reluctance",
        "reluctant",
        "reorganization",
        "restructure",
        "restructuring",
        "retaliate",
        "revoke",
        "revoked",
        "risk",
        "risks",
        "risky",
        "sanction",
        "sanctions",
        "scandal",
        "scarce",
        "scarcity",
        "setback",
        "severe",
        "severely",
        "severity",
        "shortage",
        "shortages",
        "shortcoming",
        "shortfall",
        "shrink",
        "shrinkage",
        "shut",
        "shutdown",
        "shutdowns",
        "slippage",
        "slow",
        "slowdown",
        "slowing",
        "sluggish",
        "slump",
        "stagnant",
        "stagnation",
        "strain",
        "strained",
        "stress",
        "stressed",
        "strike",
        "struggle",
        "struggled",
        "struggling",
        "subpoena",
        "substandard",
        "sue",
        "sued",
        "suffer",
        "suffered",
        "suffering",
        "susceptible",
        "suspend",
        "suspended",
        "suspension",
        "tariff",
        "tariffs",
        "terminate",
        "terminated",
        "termination",
        "theft",
        "threaten",
        "threatened",
        "threatening",
        "tighten",
        "tightening",
        "trouble",
        "troubled",
        "turmoil",
        "unable",
        "uncertain",
        "uncertainties",
        "uncertainty",
        "underfunded",
        "undermine",
        "undermined",
        "underperform",
        "underperformed",
        "unfavorable",
        "unforeseen",
        "unfortunate",
        "unfortunately",
        "unlawful",
        "unpaid",
        "unpredictable",
        "unprofitable",
        "unreliable",
        "unsafe",
        "unsatisfactory",
        "unsuccessful",
        "untimely",
        "unwarranted",
        "violate",
        "violated",
        "violation",
        "violations",
        "volatile",
        "volatility",
        "vulnerability",
        "vulnerable",
        "warn",
        "warned",
        "warning",
        "weak",
        "weaken",
        "weakened",
        "weakness",
        "worsen",
        "worsened",
        "worsening",
        "worthless",
        "writedown",
        "writeoff",
    }
)


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer. Lowercase, alpha-only tokens."""
    return [w.lower() for w in re.findall(r"[a-zA-Z]+", text)]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using simple period/exclamation/question heuristic."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in sentences if len(s.strip()) > 10]


class TranscriptAdapter:
    """Fetches earnings call transcripts and computes sentiment scores.

    Two scoring modes:
      - 'dictionary': Loughran-McDonald financial sentiment dictionary (fast, no model)
      - 'finbert': HuggingFace FinBERT model (higher quality, requires GPU/CPU inference)

    The adapter returns a DataFrame ready for nyse_core/features/nlp_earnings.py:
      columns: symbol, date, sentiment_score, sentiment_std, n_sentences
    """

    def __init__(
        self,
        scoring_mode: str = "dictionary",
        rate_limiter: SlidingWindowRateLimiter | None = None,
    ) -> None:
        if scoring_mode not in ("dictionary", "finbert"):
            raise ValueError(f"scoring_mode must be 'dictionary' or 'finbert', got '{scoring_mode}'")
        self._scoring_mode = scoring_mode
        self._rate_limiter = rate_limiter
        self._finbert_pipeline: Any = None

        # If finbert requested, try to load; fall back to dictionary
        self._effective_mode = scoring_mode
        if scoring_mode == "finbert":
            self._effective_mode = self._try_init_finbert()

    def _try_init_finbert(self) -> str:
        """Attempt to initialize FinBERT pipeline. Returns effective mode."""
        try:
            from transformers import pipeline as hf_pipeline  # noqa: F401

            self._finbert_pipeline = hf_pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                tokenizer="ProsusAI/finbert",
            )
            logger.info("FinBERT model loaded successfully.")
            return "finbert"
        except ImportError:
            logger.warning("transformers not installed; falling back to dictionary mode.")
            return "dictionary"
        except Exception as exc:
            logger.warning(f"FinBERT initialization failed ({exc}); falling back to dictionary mode.")
            return "dictionary"

    def score_text_dictionary(self, text: str) -> tuple[float, float, int]:
        """Score text using Loughran-McDonald dictionary.

        Returns (sentiment_score, sentiment_std, n_sentences).

        sentiment_score = (positive_count - negative_count) / total_word_count
        sentiment_std = std of per-sentence scores
        """
        sentences = _split_sentences(text)
        if not sentences:
            return 0.0, 0.0, 0

        sentence_scores: list[float] = []
        for sentence in sentences:
            tokens = _tokenize(sentence)
            if not tokens:
                continue
            pos = sum(1 for t in tokens if t in LM_POSITIVE_WORDS)
            neg = sum(1 for t in tokens if t in LM_NEGATIVE_WORDS)
            score = (pos - neg) / len(tokens)
            sentence_scores.append(score)

        if not sentence_scores:
            return 0.0, 0.0, 0

        doc_score = float(np.mean(sentence_scores))
        doc_std = float(np.std(sentence_scores, ddof=1)) if len(sentence_scores) > 1 else 0.0
        return doc_score, doc_std, len(sentence_scores)

    def score_text_finbert(self, text: str) -> tuple[float, float, int]:
        """Score text using FinBERT model.

        Returns (sentiment_score, sentiment_std, n_sentences).

        Maps FinBERT labels to scores: positive=+1, neutral=0, negative=-1,
        weighted by confidence.
        """
        if self._finbert_pipeline is None:
            return self.score_text_dictionary(text)

        label_map = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}

        sentences = _split_sentences(text)
        if not sentences:
            return 0.0, 0.0, 0

        # FinBERT has 512 token limit; truncate long sentences
        truncated = [s[:500] for s in sentences]

        try:
            results = self._finbert_pipeline(truncated, truncation=True)
        except Exception:
            # Fall back to dictionary on inference error
            return self.score_text_dictionary(text)

        sentence_scores: list[float] = []
        for res in results:
            label = res["label"].lower()
            confidence = res["score"]
            mapped = label_map.get(label, 0.0) * confidence
            sentence_scores.append(mapped)

        if not sentence_scores:
            return 0.0, 0.0, 0

        doc_score = float(np.mean(sentence_scores))
        doc_std = float(np.std(sentence_scores, ddof=1)) if len(sentence_scores) > 1 else 0.0
        return doc_score, doc_std, len(sentence_scores)

    def score_text(self, text: str) -> tuple[float, float, int]:
        """Score text using the configured mode.

        Returns (sentiment_score, sentiment_std, n_sentences).
        """
        if self._effective_mode == "finbert":
            return self.score_text_finbert(text)
        return self.score_text_dictionary(text)

    def fetch(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> tuple[pd.DataFrame, Diagnostics]:
        """Fetch and score earnings call transcripts for symbols.

        NOTE: Transcript source is currently stubbed. Returns a warning
        diagnostic and an empty DataFrame. Actual SEC EDGAR transcript
        fetching will be added when EDGAR adapter is extended.

        Returns DataFrame with columns:
          symbol, date, sentiment_score, sentiment_std, n_sentences
        """
        diag = Diagnostics()

        diag.warning(
            _SRC,
            "Transcript source not configured. Actual SEC EDGAR transcript "
            "fetching will be added when EDGAR adapter is extended. "
            "Use synthetic data for testing.",
            symbols_requested=len(symbols),
            start_date=str(start_date),
            end_date=str(end_date),
        )

        if self._effective_mode != self._scoring_mode:
            diag.warning(
                _SRC,
                f"Requested scoring mode '{self._scoring_mode}' not available; "
                f"using '{self._effective_mode}' instead.",
                requested=self._scoring_mode,
                effective=self._effective_mode,
            )

        diag.info(
            _SRC,
            f"TranscriptAdapter.fetch called for {len(symbols)} symbols "
            f"({start_date} to {end_date}), mode={self._effective_mode}",
            symbol_count=len(symbols),
            scoring_mode=self._effective_mode,
        )

        empty_df = pd.DataFrame(columns=_OUTPUT_COLS)
        return empty_df, diag

    @property
    def effective_mode(self) -> str:
        """The scoring mode actually in use (may differ from requested if fallback)."""
        return self._effective_mode
