"""Factor computation modules.

Exports all compute functions and provides register_all_factors() convenience
function for wiring up the FactorRegistry with correct sign conventions.
"""

from nyse_core.features.earnings import compute_earnings_surprise
from nyse_core.features.fundamental import (
    compute_accruals,
    compute_piotroski_f_score,
    compute_profitability,
)
from nyse_core.features.nlp_earnings import (
    compute_earnings_sentiment,
    compute_sentiment_dispersion,
    compute_sentiment_surprise,
)
from nyse_core.features.price_volume import (
    compute_52w_high_proximity,
    compute_ivol_20d,
    compute_momentum_2_12,
)
from nyse_core.features.registry import FactorRegistry
from nyse_core.features.short_interest import (
    compute_short_interest_change,
    compute_short_interest_pct,
    compute_short_ratio,
)
from nyse_core.schema import UsageDomain


def register_all_factors(registry: FactorRegistry) -> None:
    """Register all Tier 1 + Tier 2 factors with correct sign conventions.

    Tier 1 — Price/Volume:
      ivol_20d           sign=-1  SIGNAL  (low IVOL = buy)
      52w_high_proximity sign=+1  SIGNAL  (near high = buy)
      momentum_2_12      sign=+1  SIGNAL  (high past return = buy)

    Tier 2 — Fundamental:
      piotroski_f_score  sign=+1  SIGNAL  (high score = buy)
      accruals           sign=-1  SIGNAL  (low accruals = buy)
      profitability      sign=+1  SIGNAL  (high profitability = buy)

    Tier 2 — Earnings:
      earnings_surprise  sign=+1  SIGNAL  (positive surprise = buy)
    """
    # Tier 1: Price/Volume
    registry.register(
        name="ivol_20d",
        compute_fn=compute_ivol_20d,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=-1,
        description="Idiosyncratic volatility (20-day std of returns). Low IVOL = buy.",
    )
    registry.register(
        name="52w_high_proximity",
        compute_fn=compute_52w_high_proximity,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=1,
        description="Proximity to 52-week high (close / 52w max). Near high = buy.",
    )
    registry.register(
        name="momentum_2_12",
        compute_fn=compute_momentum_2_12,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=1,
        description="Momentum 2-12 (return from 12m to 1m ago). High past return = buy.",
    )

    # Tier 2: Fundamental (data_source="fundamentals" -> EDGAR XBRL)
    registry.register(
        name="piotroski_f_score",
        compute_fn=compute_piotroski_f_score,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=1,
        description="Piotroski F-score (0-9). High score = buy.",
        data_source="fundamentals",
    )
    registry.register(
        name="accruals",
        compute_fn=compute_accruals,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=-1,
        description="Accruals ratio. Low accruals = buy (quality earnings).",
        data_source="fundamentals",
    )
    registry.register(
        name="profitability",
        compute_fn=compute_profitability,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=1,
        description="Fama-French operating profitability. High = buy.",
        data_source="fundamentals",
    )

    # Tier 2: Earnings (data_source="fundamentals" -> EDGAR XBRL)
    registry.register(
        name="earnings_surprise",
        compute_fn=compute_earnings_surprise,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=1,
        description="Standardized Unexpected Earnings (SUE). Positive surprise = buy.",
        data_source="fundamentals",
    )

    # Tier 3: NLP Earnings Sentiment (data_source="transcripts")
    registry.register(
        name="earnings_sentiment",
        compute_fn=compute_earnings_sentiment,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=1,
        description="NLP earnings call sentiment. Positive sentiment = buy.",
        data_source="transcripts",
    )
    registry.register(
        name="sentiment_surprise",
        compute_fn=compute_sentiment_surprise,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=1,
        description="Sentiment surprise (current - 4Q rolling mean). Improving = buy.",
        data_source="transcripts",
    )
    registry.register(
        name="sentiment_dispersion",
        compute_fn=compute_sentiment_dispersion,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=-1,
        description="Sentence-level sentiment dispersion. High dispersion = sell.",
        data_source="transcripts",
    )

    # Tier 2: Short Interest (data_source="short_interest" -> FINRA)
    registry.register(
        name="short_ratio",
        compute_fn=compute_short_ratio,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=-1,
        description="Short ratio (days to cover). High short ratio = sell.",
        data_source="short_interest",
    )
    registry.register(
        name="short_interest_pct",
        compute_fn=compute_short_interest_pct,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=-1,
        description="Short interest as % of shares outstanding. High = sell.",
        data_source="short_interest",
    )
    registry.register(
        name="short_interest_change",
        compute_fn=compute_short_interest_change,
        usage_domain=UsageDomain.SIGNAL,
        sign_convention=-1,
        description="Change in short interest. Increasing = sell.",
        data_source="short_interest",
    )


__all__ = [
    "compute_ivol_20d",
    "compute_52w_high_proximity",
    "compute_momentum_2_12",
    "compute_piotroski_f_score",
    "compute_accruals",
    "compute_profitability",
    "compute_earnings_surprise",
    "compute_earnings_sentiment",
    "compute_sentiment_surprise",
    "compute_sentiment_dispersion",
    "compute_short_ratio",
    "compute_short_interest_pct",
    "compute_short_interest_change",
    "register_all_factors",
]
