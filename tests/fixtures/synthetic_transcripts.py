"""Synthetic earnings call transcript sentiment data generator.

Generates realistic pre-computed sentiment scores at quarterly frequency
for testing nyse_core/features/nlp_earnings.py factors.

Three stock profiles:
  - Improving: sentiment trends upward over quarters
  - Stable: sentiment stays roughly constant
  - Deteriorating: sentiment trends downward over quarters
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd


def generate_transcript_sentiments(
    symbols: list[str],
    n_quarters: int = 8,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic transcript sentiment scores.

    Returns DataFrame with columns:
      symbol, date, sentiment_score, sentiment_std, n_sentences

    - sentiment_score: -1.0 to +1.0 (correlated with stock's quality profile)
    - sentiment_std: 0.1 to 0.8 (higher for mixed-signal transcripts)
    - n_sentences: 50-300 (realistic transcript length)
    - Quarterly frequency matching earnings dates

    Stock profiles are assigned deterministically:
      - First third of symbols: IMPROVING (upward trend)
      - Second third: STABLE (flat, moderate sentiment)
      - Last third: DETERIORATING (downward trend)

    Parameters
    ----------
    symbols : list[str]
        List of stock symbols to generate data for.
    n_quarters : int
        Number of quarters of history (default 8 = 2 years).
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        Columns: symbol, date, sentiment_score, sentiment_std, n_sentences.
        Sorted by (symbol, date).
    """
    rng = np.random.default_rng(seed)

    # Calendar quarter-end dates
    quarter_ends = pd.date_range(
        end="2024-12-31",
        periods=n_quarters,
        freq="QE",
    )

    # Earnings call dates: ~30 days after quarter end
    n_symbols = len(symbols)
    n_improving = max(1, n_symbols // 3)
    n_stable = max(1, n_symbols // 3)
    # Rest are deteriorating

    records: list[dict] = []

    for i, sym in enumerate(symbols):
        # Determine profile
        if i < n_improving:
            profile = "improving"
        elif i < n_improving + n_stable:
            profile = "stable"
        else:
            profile = "deteriorating"

        for q_idx, q_end in enumerate(quarter_ends):
            # Earnings call date: 25-40 days after quarter end
            lag_days = rng.integers(25, 41)
            call_date = q_end + timedelta(days=int(lag_days))

            # Base sentiment by profile
            if profile == "improving":
                # Start around -0.1, trend to +0.4 over n_quarters
                base = -0.1 + 0.5 * (q_idx / max(n_quarters - 1, 1))
            elif profile == "stable":
                # Hover around +0.15
                base = 0.15
            else:
                # Start around +0.3, trend to -0.2 over n_quarters
                base = 0.3 - 0.5 * (q_idx / max(n_quarters - 1, 1))

            # Add noise
            noise = rng.normal(0, 0.08)
            sentiment_score = float(np.clip(base + noise, -1.0, 1.0))

            # Sentiment std: higher for deteriorating stocks (mixed signals)
            if profile == "deteriorating":
                base_std = 0.4 + 0.2 * (q_idx / max(n_quarters - 1, 1))
            elif profile == "stable":
                base_std = 0.2
            else:
                base_std = 0.3 - 0.1 * (q_idx / max(n_quarters - 1, 1))

            sentiment_std = float(
                np.clip(
                    base_std + rng.normal(0, 0.05),
                    0.05,
                    0.85,
                )
            )

            # Number of sentences: 50-300 (larger companies have longer calls)
            n_sentences = int(rng.integers(50, 301))

            records.append(
                {
                    "symbol": sym,
                    "date": call_date.date(),
                    "sentiment_score": round(sentiment_score, 4),
                    "sentiment_std": round(sentiment_std, 4),
                    "n_sentences": n_sentences,
                }
            )

    df = pd.DataFrame(records)
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    return df
