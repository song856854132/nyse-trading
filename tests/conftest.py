"""Root conftest.py — shared fixtures for all test directories.

All fixtures generate deterministic synthetic data via seed=42.
Fixtures delegate to the standalone generators in tests/fixtures/ so that
data generation logic is importable outside of pytest as well.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from tests.fixtures.synthetic_constituency import generate_constituency_changes
from tests.fixtures.synthetic_corporate_actions import generate_corporate_actions
from tests.fixtures.synthetic_fundamentals import generate_fundamentals
from tests.fixtures.synthetic_prices import generate_prices, generate_spy_prices
from tests.fixtures.synthetic_transcripts import generate_transcript_sentiments

if TYPE_CHECKING:
    import pandas as pd

# ── GICS Sector Mapping ─────────────────────────────────────────────────────

_GICS_SECTORS = [
    "Information Technology",
    "Health Care",
    "Financials",
    "Consumer Discretionary",
    "Industrials",
]


def _build_sector_map(symbols: list[str], seed: int = 42) -> dict[str, str]:
    """Deterministically assign symbols to GICS sectors (round-robin + jitter)."""
    rng = np.random.default_rng(seed)
    shuffled = list(symbols)
    rng.shuffle(shuffled)
    return {sym: _GICS_SECTORS[i % len(_GICS_SECTORS)] for i, sym in enumerate(shuffled)}


# ── Price Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_prices() -> pd.DataFrame:
    """50 stocks x 600 trading days of realistic OHLCV data.

    Includes:
    - Proper OHLCV relationships (high >= open, close; low <= open, close)
    - Stocks with missing days (trading gaps)
    - Stocks with zero-volume days
    - 3 stocks with insufficient history (recently listed)
    """
    return generate_prices(n_stocks=50, n_days=600, seed=42)


@pytest.fixture
def synthetic_prices_small() -> pd.DataFrame:
    """10 stocks x 100 trading days -- lightweight fixture for fast tests."""
    return generate_prices(n_stocks=10, n_days=100, seed=42)


@pytest.fixture
def synthetic_spy_prices() -> pd.DataFrame:
    """SPY benchmark with SMA200 crossing events (both BULL and BEAR regimes)."""
    return generate_spy_prices(n_days=600, seed=42)


# ── Fundamental Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def synthetic_fundamentals(synthetic_prices: pd.DataFrame) -> pd.DataFrame:
    """Quarterly long-format XBRL facts for all symbols in synthetic_prices.

    Columns: date, symbol, metric_name, value, filing_type, period_end
    (matches EdgarAdapter.fetch output schema).

    Emits one row per (symbol, period_end) × metric for the ten metrics
    consumed by the fundamental factor compute functions.
    """
    symbols = sorted(synthetic_prices["symbol"].unique().tolist())
    return generate_fundamentals(symbols=symbols, n_quarters=20, seed=42)


# ── Sector Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_sectors(synthetic_prices: pd.DataFrame) -> dict[str, str]:
    """Dict mapping symbol to GICS sector. 5 sectors, roughly equal distribution."""
    symbols = sorted(synthetic_prices["symbol"].unique().tolist())
    return _build_sector_map(symbols, seed=42)


# ── Constituency Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def synthetic_constituency_changes(synthetic_prices: pd.DataFrame) -> pd.DataFrame:
    """S&P 500 membership ADD/REMOVE events.

    20 changes across ~3 years, starting from the synthetic_prices symbol set.
    """
    symbols = sorted(synthetic_prices["symbol"].unique().tolist())
    return generate_constituency_changes(
        initial_members=symbols,
        n_changes=20,
        seed=42,
    )


# ── Corporate Action Fixtures ────────────────────────────────────────────────


@pytest.fixture
def synthetic_transcript_sentiments(synthetic_prices: pd.DataFrame) -> pd.DataFrame:
    """Quarterly earnings call sentiment scores for all symbols.

    Columns: symbol, date, sentiment_score, sentiment_std, n_sentences.
    Three profiles: improving, stable, deteriorating sentiment.
    """
    symbols = sorted(synthetic_prices["symbol"].unique().tolist())
    return generate_transcript_sentiments(symbols=symbols, n_quarters=8, seed=42)


@pytest.fixture
def synthetic_corporate_actions(synthetic_prices: pd.DataFrame) -> pd.DataFrame:
    """Stock splits and dividends for a subset of synthetic_prices symbols."""
    symbols = sorted(synthetic_prices["symbol"].unique().tolist())
    return generate_corporate_actions(symbols=symbols, seed=42)
