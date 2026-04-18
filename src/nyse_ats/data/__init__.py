"""Data adapters for external data sources.

Public API:
- DataAdapter: Protocol for all adapters
- SlidingWindowRateLimiter: Thread-safe sliding-window rate limiter
- FinMindAdapter: FinMind OHLCV data
- EdgarAdapter: SEC EDGAR fundamentals
- FinraAdapter: FINRA short interest
- ConstituencyAdapter: S&P 500 historical membership
- VendorRegistry: Config-driven adapter factory
"""

from nyse_ats.data.adapter import DataAdapter
from nyse_ats.data.constituency_adapter import ConstituencyAdapter
from nyse_ats.data.edgar_adapter import EdgarAdapter
from nyse_ats.data.finmind_adapter import FinMindAdapter
from nyse_ats.data.finra_adapter import FinraAdapter
from nyse_ats.data.rate_limiter import SlidingWindowRateLimiter
from nyse_ats.data.transcript_adapter import TranscriptAdapter
from nyse_ats.data.vendor_registry import VendorRegistry

__all__ = [
    "DataAdapter",
    "SlidingWindowRateLimiter",
    "FinMindAdapter",
    "EdgarAdapter",
    "FinraAdapter",
    "ConstituencyAdapter",
    "TranscriptAdapter",
    "VendorRegistry",
]
