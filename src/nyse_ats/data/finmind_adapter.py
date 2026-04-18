"""FinMind OHLCV data adapter.

Fetches US stock price data from the FinMind API and maps to canonical
column names defined in nyse_core.schema.
"""

from __future__ import annotations

import os
import re
from datetime import date, timedelta
from typing import TYPE_CHECKING

import pandas as pd
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from nyse_core.contracts import Diagnostics
from nyse_core.schema import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_SYMBOL,
    COL_VOLUME,
)

if TYPE_CHECKING:
    from nyse_ats.data.rate_limiter import SlidingWindowRateLimiter
    from nyse_core.config_schema import FinMindConfig

_SRC = "finmind_adapter"

# ── FinMind column name mapping ──────────────────────────────────────────────

_FINMIND_COL_MAP: dict[str, str] = {
    # Date aliases seen across FinMind datasets
    "Trading_Date": COL_DATE,
    "Trading_date": COL_DATE,
    "date": COL_DATE,
    "stock_id": COL_SYMBOL,
    # TWSE dataset convention (lowercase open/max/min/close)
    "open": COL_OPEN,
    "max": COL_HIGH,
    "min": COL_LOW,
    "close": COL_CLOSE,
    "Trading_Volume": COL_VOLUME,
    # USStockPrice dataset convention (capitalized, High/Low not max/min)
    "Open": COL_OPEN,
    "High": COL_HIGH,
    "Low": COL_LOW,
    "Close": COL_CLOSE,
    "Volume": COL_VOLUME,
}

_CANONICAL_OHLCV = [
    COL_DATE,
    COL_SYMBOL,
    COL_OPEN,
    COL_HIGH,
    COL_LOW,
    COL_CLOSE,
    COL_VOLUME,
]


class FinMindAdapterError(Exception):
    """Raised when the FinMind API returns an unexpected response."""


class FinMindAdapter:
    """Adapter for FinMind USStockPrice dataset.

    Parameters
    ----------
    config : FinMindConfig
        Validated configuration from data_sources.yaml.
    rate_limiter : SlidingWindowRateLimiter
        Shared rate limiter for FinMind API calls.
    session : requests.Session | None
        Optional session for dependency injection / testing.
    """

    def __init__(
        self,
        config: FinMindConfig,
        rate_limiter: SlidingWindowRateLimiter,
        session: requests.Session | None = None,
    ) -> None:
        self._config = config
        self._rate_limiter = rate_limiter
        self._session = session or requests.Session()
        self._data_url = f"{config.base_url}/data"

    def _get_token(self) -> str:
        """Read API token from environment variable."""
        token = os.environ.get(self._config.token_env_var, "")
        return token

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        reraise=True,
    )
    def _request_symbol(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        diag: Diagnostics,
    ) -> pd.DataFrame:
        """Fetch OHLCV data for a single symbol with retry + rate limiting."""
        self._rate_limiter.acquire()

        params = {
            "dataset": self._config.datasets.get("ohlcv", "USStockPrice"),
            "data_id": symbol,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "token": self._get_token(),
        }

        resp = self._session.get(self._data_url, params=params, timeout=30)

        if resp.status_code == 429:
            diag.warning(
                _SRC,
                f"Rate limited by FinMind (429) for {symbol}",
                symbol=symbol,
            )
            raise requests.ConnectionError("Rate limited by FinMind (429)")

        resp.raise_for_status()

        payload = resp.json()
        if payload.get("status") != 200 and payload.get("msg") != "success":
            msg = payload.get("msg", "unknown error")
            diag.warning(
                _SRC,
                f"FinMind API error for {symbol}: {msg}",
                symbol=symbol,
                api_msg=msg,
            )
            return pd.DataFrame(columns=_CANONICAL_OHLCV)

        data = payload.get("data", [])
        if not data:
            diag.info(
                _SRC,
                f"No data returned for {symbol} ({start_date} to {end_date})",
                symbol=symbol,
            )
            return pd.DataFrame(columns=_CANONICAL_OHLCV)

        df = pd.DataFrame(data)
        return self._normalize(df, symbol, diag)

    def _normalize(self, df: pd.DataFrame, symbol: str, diag: Diagnostics) -> pd.DataFrame:
        """Map FinMind column names to canonical names and validate."""
        # Rename columns that exist in the mapping
        rename_map = {k: v for k, v in _FINMIND_COL_MAP.items() if k in df.columns}
        df = df.rename(columns=rename_map)

        # Ensure symbol column is set
        if COL_SYMBOL not in df.columns:
            df[COL_SYMBOL] = symbol

        # Parse date
        if COL_DATE in df.columns:
            df[COL_DATE] = pd.to_datetime(df[COL_DATE]).dt.date

        # Keep only canonical columns that are present
        present = [c for c in _CANONICAL_OHLCV if c in df.columns]
        df = df[present].copy()

        # Add any missing canonical columns as NaN
        for col in _CANONICAL_OHLCV:
            if col not in df.columns:
                df[col] = float("nan")

        # Numeric coercion
        for col in [COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # OHLCV validation: high >= max(open, close), low <= min(open, close)
        df = self._validate_ohlcv(df, symbol, diag)

        return df[_CANONICAL_OHLCV]

    def _validate_ohlcv(self, df: pd.DataFrame, symbol: str, diag: Diagnostics) -> pd.DataFrame:
        """Validate OHLCV constraints and log violations."""
        if df.empty:
            return df

        high_violation = df[COL_HIGH] < df[[COL_OPEN, COL_CLOSE]].max(axis=1)
        low_violation = df[COL_LOW] > df[[COL_OPEN, COL_CLOSE]].min(axis=1)

        n_high = int(high_violation.sum())
        n_low = int(low_violation.sum())

        if n_high > 0:
            diag.warning(
                _SRC,
                f"{symbol}: {n_high} rows where high < max(open, close)",
                symbol=symbol,
                violation_count=n_high,
            )

        if n_low > 0:
            diag.warning(
                _SRC,
                f"{symbol}: {n_low} rows where low > min(open, close)",
                symbol=symbol,
                violation_count=n_low,
            )

        # Check for date gaps (weekdays only)
        if COL_DATE in df.columns and len(df) > 1:
            dates = pd.to_datetime(pd.Series([d for d in df[COL_DATE]]))
            dates_sorted = dates.sort_values().reset_index(drop=True)
            diffs = dates_sorted.diff().dropna()
            # Flag gaps > 3 calendar days (weekends are 2 days, >3 means missing)
            gaps = diffs[diffs > pd.Timedelta(days=4)]
            if len(gaps) > 0:
                diag.warning(
                    _SRC,
                    f"{symbol}: {len(gaps)} trading day gap(s) detected",
                    symbol=symbol,
                    gap_count=len(gaps),
                )

        return df

    def fetch(self, symbols: list[str], start_date: date, end_date: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Fetch OHLCV data for a list of symbols.

        Returns a DataFrame with canonical columns:
        date, symbol, open, high, low, close, volume.
        """
        diag = Diagnostics()
        frames: list[pd.DataFrame] = []

        diag.info(
            _SRC,
            f"Fetching OHLCV for {len(symbols)} symbols ({start_date} to {end_date})",
            symbol_count=len(symbols),
        )

        for sym in symbols:
            try:
                df = self._request_symbol(sym, start_date, end_date, diag)
                if not df.empty:
                    frames.append(df)
            except Exception as exc:
                # Per-symbol failure is partial success, not system failure —
                # downgrade to warning so the batch still persists. Scrub the
                # token from the exception string (FinMind embeds it in the
                # GET URL, which shows up in requests.HTTPError messages).
                scrubbed = re.sub(r"token=[A-Za-z0-9._\-]+", "token=<REDACTED>", str(exc))
                diag.warning(
                    _SRC,
                    f"Failed to fetch data for {sym}: {scrubbed}",
                    symbol=sym,
                )

        if not frames:
            diag.warning(_SRC, "No data returned for any symbol")
            return pd.DataFrame(columns=_CANONICAL_OHLCV), diag

        result = pd.concat(frames, ignore_index=True)
        diag.info(
            _SRC,
            f"Fetched {len(result)} total rows for {len(frames)} symbols",
            row_count=len(result),
            symbol_count=len(frames),
        )
        return result, diag

    def fetch_incremental(self, symbols: list[str], since: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Incremental daily update since *since*.

        Fetches data from *since* to today.
        """
        end_date = date.today()
        if since >= end_date:
            diag = Diagnostics()
            diag.info(
                _SRC,
                f"Incremental fetch: since={since} >= today, nothing to fetch",
            )
            return pd.DataFrame(columns=_CANONICAL_OHLCV), diag

        return self.fetch(symbols, since + timedelta(days=1), end_date)

    def health_check(self) -> tuple[bool, Diagnostics]:
        """Check if the FinMind API is reachable."""
        diag = Diagnostics()
        try:
            resp = self._session.get(self._config.base_url, timeout=10)
            healthy = resp.status_code < 500
            if healthy:
                diag.info(_SRC, "FinMind API health check passed")
            else:
                diag.error(
                    _SRC,
                    f"FinMind API returned status {resp.status_code}",
                )
            return healthy, diag
        except Exception as exc:
            diag.error(_SRC, f"FinMind health check failed: {exc}")
            return False, diag
