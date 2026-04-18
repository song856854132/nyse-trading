"""FINRA Short Interest data adapter.

Fetches short interest data from the FINRA API. Critical PiT rule: FINRA has
an 11-day publication lag. The adapter records BOTH the settlement_date (when
data was observed) and the publication_date (settlement + lag days). The
``date`` column is the settlement_date; PiT enforcement in nyse_core handles
the rest.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import pandas as pd
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_DATE, COL_SYMBOL

if TYPE_CHECKING:
    from nyse_ats.data.rate_limiter import SlidingWindowRateLimiter
    from nyse_core.config_schema import FinraConfig

_SRC = "finra_adapter"

# ── Output column names ──────────────────────────────────────────────────────

COL_SHORT_INTEREST = "short_interest"
COL_DAYS_TO_COVER = "days_to_cover"
COL_SHORT_RATIO = "short_ratio"
COL_PUBLICATION_DATE = "publication_date"

_OUTPUT_COLS = [
    COL_DATE,
    COL_SYMBOL,
    COL_SHORT_INTEREST,
    COL_DAYS_TO_COVER,
    COL_SHORT_RATIO,
]


class FinraAdapterError(Exception):
    """Raised when the FINRA API returns an unexpected response."""


class FinraAdapter:
    """Adapter for FINRA short interest data.

    Parameters
    ----------
    config : FinraConfig
        Validated FINRA configuration from data_sources.yaml.
    rate_limiter : SlidingWindowRateLimiter
        Shared rate limiter for FINRA API calls.
    session : requests.Session | None
        Optional session for dependency injection / testing.
    """

    def __init__(
        self,
        config: FinraConfig,
        rate_limiter: SlidingWindowRateLimiter,
        session: requests.Session | None = None,
    ) -> None:
        self._config = config
        self._rate_limiter = rate_limiter
        self._session = session or requests.Session()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        reraise=True,
    )
    def _request_short_interest(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        diag: Diagnostics,
    ) -> list[dict[str, Any]]:
        """Fetch short interest data from FINRA API with retry."""
        self._rate_limiter.acquire()

        payload = {
            "fields": [
                "symbolCode",
                "settlementDate",
                "currentShortPositionQuantity",
                "daysToCoverQuantity",
                "shortInterestRatioQuantity",
            ],
            "dateRangeFilters": [
                {
                    "fieldName": "settlementDate",
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                }
            ],
            "domainFilters": [
                {
                    "fieldName": "symbolCode",
                    "values": symbols,
                }
            ],
        }

        resp = self._session.post(
            self._config.short_interest_url,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()

        data = resp.json()
        diag.debug(
            _SRC,
            f"FINRA returned {len(data)} short interest records",
            record_count=len(data),
        )
        return data

    def _parse_records(
        self,
        records: list[dict[str, Any]],
        diag: Diagnostics,
    ) -> pd.DataFrame:
        """Parse FINRA API response into canonical DataFrame.

        Critical PiT rule: adds publication_date = settlement_date + lag days.
        The ``date`` column is the settlement_date.
        """
        if not records:
            return pd.DataFrame(columns=_OUTPUT_COLS)

        rows: list[dict[str, Any]] = []
        lag_days = self._config.publication_lag_days

        for record in records:
            try:
                settlement_str = record.get("settlementDate", "")
                if not settlement_str:
                    continue

                settlement_date = pd.to_datetime(settlement_str).date()
                publication_date = settlement_date + timedelta(days=lag_days)

                symbol = record.get("symbolCode", "")
                if not symbol:
                    continue

                rows.append(
                    {
                        COL_DATE: settlement_date,
                        COL_SYMBOL: symbol,
                        COL_SHORT_INTEREST: self._safe_float(record.get("currentShortPositionQuantity")),
                        COL_DAYS_TO_COVER: self._safe_float(record.get("daysToCoverQuantity")),
                        COL_SHORT_RATIO: self._safe_float(record.get("shortInterestRatioQuantity")),
                        COL_PUBLICATION_DATE: publication_date,
                    }
                )
            except Exception as exc:
                diag.warning(
                    _SRC,
                    f"Failed to parse FINRA record: {exc}",
                )

        if not rows:
            return pd.DataFrame(columns=_OUTPUT_COLS)

        return pd.DataFrame(rows)

    @staticmethod
    def _safe_float(val: Any) -> float:
        """Convert a value to float, returning NaN on failure."""
        if val is None:
            return float("nan")
        try:
            return float(val)
        except (TypeError, ValueError):
            return float("nan")

    def fetch(self, symbols: list[str], start_date: date, end_date: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Fetch short interest data from FINRA API.

        Returns DataFrame: date (settlement), symbol, short_interest,
        days_to_cover, short_ratio. A publication_date column is also
        included for PiT enforcement.
        """
        diag = Diagnostics()

        diag.info(
            _SRC,
            f"Fetching FINRA short interest for {len(symbols)} symbols ({start_date} to {end_date})",
            symbol_count=len(symbols),
        )

        try:
            records = self._request_short_interest(symbols, start_date, end_date, diag)
        except Exception as exc:
            diag.error(
                _SRC,
                f"FINRA API request failed: {exc}",
            )
            return pd.DataFrame(columns=_OUTPUT_COLS), diag

        df = self._parse_records(records, diag)

        if df.empty:
            diag.warning(_SRC, "No short interest data returned")
            return pd.DataFrame(columns=_OUTPUT_COLS), diag

        diag.info(
            _SRC,
            f"Fetched {len(df)} short interest records",
            row_count=len(df),
        )
        return df, diag

    def fetch_incremental(self, symbols: list[str], since: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Incremental fetch for short interest data since *since*."""
        end_date = date.today()
        if since >= end_date:
            diag = Diagnostics()
            diag.info(
                _SRC,
                f"Incremental fetch: since={since} >= today, nothing to fetch",
            )
            return pd.DataFrame(columns=_OUTPUT_COLS), diag
        return self.fetch(symbols, since + timedelta(days=1), end_date)

    def health_check(self) -> tuple[bool, Diagnostics]:
        """Check if the FINRA API is reachable."""
        diag = Diagnostics()
        try:
            resp = self._session.get(self._config.short_interest_url, timeout=10)
            # FINRA may return 405 for GET on a POST endpoint -- still reachable
            healthy = resp.status_code < 500
            if healthy:
                diag.info(_SRC, "FINRA API health check passed")
            else:
                diag.error(
                    _SRC,
                    f"FINRA API returned status {resp.status_code}",
                )
            return healthy, diag
        except Exception as exc:
            diag.error(_SRC, f"FINRA health check failed: {exc}")
            return False, diag
