"""SEC EDGAR XBRL adapter — companyfacts API.

Fetches fundamental data by reading the per-CIK XBRL companyfacts JSON at
``data.sec.gov/api/xbrl/companyfacts/CIK##########.json``. This is the
authoritative SEC endpoint for structured XBRL facts across all of a
company's historical filings.

Design notes
------------
- **One API call per symbol.** Companyfacts is a single JSON payload
  containing every reported tag across every filing, so we pay one
  round-trip per symbol regardless of date range.
- **CIK resolution.** The SEC XBRL endpoints key by CIK, not ticker.
  Callers should inject a ``ticker_cik_map`` (symbol → int CIK). When
  omitted, the adapter lazy-fetches the canonical
  ``www.sec.gov/files/company_tickers.json`` once and caches it.
- **Period disambiguation.** Flow metrics (revenue, NI, CFO, …) appear
  in companyfacts multiple times per fiscal year — quarterly, YTD, and
  annual rollups all live in the same ``units`` list. We filter by
  ``(period_end - period_start)`` so 10-Q rows keep quarterly slices and
  10-K rows keep annual slices. Balance-sheet (point-in-time) metrics
  have no ``start`` field and pass through unfiltered.
- **Deduplication.** Several XBRL tags can map to the same canonical
  metric (e.g. both ``Revenues`` and
  ``RevenueFromContractWithCustomerExcludingAssessedTax``). First tag in
  ``_XBRL_TAG_MAP`` wins for a given (metric, period_end, filed, form).
"""

from __future__ import annotations

import os
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
    from nyse_core.config_schema import EdgarConfig

_SRC = "edgar_adapter"

# ── Output column names ──────────────────────────────────────────────────────

COL_METRIC_NAME = "metric_name"
COL_VALUE = "value"
COL_FILING_TYPE = "filing_type"
COL_PERIOD_END = "period_end"

_OUTPUT_COLS = [
    COL_DATE,
    COL_SYMBOL,
    COL_METRIC_NAME,
    COL_VALUE,
    COL_FILING_TYPE,
    COL_PERIOD_END,
]

# ── SEC endpoints (base_url-relative) ────────────────────────────────────────

_COMPANYFACTS_PATH = "/api/xbrl/companyfacts/CIK{cik:010d}.json"
_TICKERS_URL_DEFAULT = "https://www.sec.gov/files/company_tickers.json"

# ── XBRL tag → canonical metric name ─────────────────────────────────────────
# Insertion order matters: first tag for a metric wins when multiple map to
# the same canonical name (e.g. Revenues before newer
# RevenueFromContractWithCustomerExcludingAssessedTax).

_XBRL_TAG_MAP: dict[str, str] = {
    # Income statement (flow)
    "Revenues": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "SalesRevenueNet": "revenue",
    "NetIncomeLoss": "net_income",
    "GrossProfit": "gross_profit",
    "CostOfRevenue": "cost_of_revenue",
    "CostOfGoodsAndServicesSold": "cost_of_revenue",
    "CostOfGoodsSold": "cost_of_revenue",
    # Balance sheet (point-in-time)
    "Assets": "total_assets",
    "AssetsCurrent": "current_assets",
    "Liabilities": "total_liabilities",
    "LiabilitiesCurrent": "current_liabilities",
    "LongTermDebtNoncurrent": "long_term_debt",
    "LongTermDebt": "long_term_debt",
    # Cash flow (flow)
    "NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
    # Shares (PiT preferred; weighted-average fallback)
    "CommonStockSharesOutstanding": "shares_outstanding",
    "EntityCommonStockSharesOutstanding": "shares_outstanding",
    "WeightedAverageNumberOfSharesOutstandingBasic": "shares_outstanding",
    # Per-share
    "EarningsPerShareBasic": "eps",
    "EarningsPerShareDiluted": "eps",
}

# Flow metrics need (end - start) window filtering so 10-Q rows keep quarterly
# slices and 10-K rows keep annual slices. PiT metrics pass through.
_FLOW_METRICS: set[str] = {
    "revenue",
    "net_income",
    "gross_profit",
    "cost_of_revenue",
    "operating_cash_flow",
    "eps",
}

# Units by metric. Anything not listed here is interpreted as "USD".
_SHARES_METRICS: set[str] = {"shares_outstanding"}
_USD_PER_SHARE_METRICS: set[str] = {"eps"}

# Period-length windows (days) for disambiguating quarterly vs YTD vs annual.
_QUARTERLY_MIN, _QUARTERLY_MAX = 80, 100
_ANNUAL_MIN, _ANNUAL_MAX = 350, 380


class EdgarAdapterError(Exception):
    """Raised when an EDGAR API call fails unexpectedly."""


class EdgarAdapter:
    """Adapter for SEC EDGAR fundamental data via the companyfacts API.

    Parameters
    ----------
    config : EdgarConfig
        Validated EDGAR configuration from ``data_sources.yaml``.
        ``config.base_url`` should point at ``https://data.sec.gov``.
    rate_limiter : SlidingWindowRateLimiter
        Sliding-window limiter (10 req/s per SEC fair-use policy).
    session : requests.Session | None
        Optional session for dependency injection / testing.
    ticker_cik_map : dict[str, int] | None
        Optional pre-built ticker → CIK mapping. When None, the adapter
        lazy-fetches ``company_tickers.json`` from sec.gov on first use.
    """

    def __init__(
        self,
        config: EdgarConfig,
        rate_limiter: SlidingWindowRateLimiter,
        session: requests.Session | None = None,
        ticker_cik_map: dict[str, int] | None = None,
    ) -> None:
        self._config = config
        self._rate_limiter = rate_limiter
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": self._get_user_agent()})
        self._ticker_cik_map: dict[str, int] | None = (
            dict(ticker_cik_map) if ticker_cik_map is not None else None
        )

    def _get_user_agent(self) -> str:
        ua = os.environ.get(self._config.user_agent_env_var, "")
        if not ua:
            ua = "nyse-ats-bot contact@example.com"
        return ua

    # ── CIK resolution ───────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        reraise=True,
    )
    def _fetch_ticker_map(self, diag: Diagnostics) -> dict[str, int]:
        """Fetch canonical ticker → CIK mapping from sec.gov once, cache."""
        self._rate_limiter.acquire()
        resp = self._session.get(_TICKERS_URL_DEFAULT, timeout=30)
        resp.raise_for_status()
        raw = resp.json()
        # Format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": ...}, ...}
        mapping: dict[str, int] = {}
        for entry in raw.values():
            try:
                ticker = str(entry["ticker"]).upper()
                mapping[ticker] = int(entry["cik_str"])
            except (KeyError, TypeError, ValueError):
                continue
        diag.debug(
            _SRC,
            f"Fetched ticker→CIK map ({len(mapping)} entries)",
            entry_count=len(mapping),
        )
        return mapping

    def _resolve_cik(self, symbol: str, diag: Diagnostics) -> int | None:
        if self._ticker_cik_map is None:
            try:
                self._ticker_cik_map = self._fetch_ticker_map(diag)
            except Exception as exc:
                diag.error(
                    _SRC,
                    f"Failed to fetch ticker→CIK map: {exc}",
                )
                self._ticker_cik_map = {}
        return self._ticker_cik_map.get(symbol.upper())

    # ── Companyfacts fetch ───────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        reraise=True,
    )
    def _fetch_companyfacts(self, cik: int, diag: Diagnostics) -> dict[str, Any] | None:
        """Fetch companyfacts JSON for one CIK. Returns None on 404."""
        self._rate_limiter.acquire()
        url = f"{self._config.base_url}{_COMPANYFACTS_PATH.format(cik=cik)}"
        resp = self._session.get(url, timeout=30)
        if resp.status_code == 404:
            diag.warning(
                _SRC,
                f"No companyfacts document for CIK {cik}",
                cik=cik,
            )
            return None
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    # ── Fact extraction ──────────────────────────────────────────────────

    def _select_units(self, metric_name: str, units: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        if metric_name in _SHARES_METRICS:
            return units.get("shares", [])
        if metric_name in _USD_PER_SHARE_METRICS:
            return units.get("USD/shares", [])
        return units.get("USD", [])

    def _is_period_acceptable(
        self,
        metric_name: str,
        form: str,
        period_start: date | None,
        period_end: date,
    ) -> bool:
        """Flow metrics: filter by period length to match form granularity.

        PiT metrics pass through. For flow metrics, 10-Q keeps quarterly
        (80-100d) rows and 10-K keeps annual (350-380d) rows — which
        discards YTD rollups and cross-form duplicates.
        """
        if metric_name not in _FLOW_METRICS:
            return True
        if period_start is None:
            return False
        days = (period_end - period_start).days
        if form == "10-Q":
            return _QUARTERLY_MIN <= days <= _QUARTERLY_MAX
        if form == "10-K":
            return _ANNUAL_MIN <= days <= _ANNUAL_MAX
        return False

    def _parse_companyfacts(
        self,
        cf_data: dict[str, Any] | None,
        symbol: str,
        start_date: date,
        end_date: date,
        filing_types: list[str],
        diag: Diagnostics,
    ) -> list[dict[str, Any]]:
        """Extract long-format rows from a single companyfacts JSON payload."""
        rows: list[dict[str, Any]] = []
        if not cf_data:
            return rows

        us_gaap = cf_data.get("facts", {}).get("us-gaap", {})
        if not us_gaap:
            diag.warning(
                _SRC,
                f"companyfacts for {symbol} has no us-gaap facts",
                symbol=symbol,
            )
            return rows

        # (metric, period_end, filed, form) — first tag wins
        seen: set[tuple[str, date, date, str]] = set()

        for xbrl_tag, metric_name in _XBRL_TAG_MAP.items():
            tag_data = us_gaap.get(xbrl_tag)
            if not tag_data:
                continue
            units_dict = tag_data.get("units", {})
            if not isinstance(units_dict, dict):
                continue
            unit_list = self._select_units(metric_name, units_dict)
            if not unit_list:
                continue

            for fact in unit_list:
                if not isinstance(fact, dict):
                    continue
                form = fact.get("form", "")
                if form not in filing_types:
                    continue
                filed_raw = fact.get("filed")
                if not filed_raw:
                    continue
                try:
                    filed = pd.to_datetime(filed_raw).date()
                except (ValueError, TypeError):
                    continue
                if filed < start_date or filed > end_date:
                    continue

                end_raw = fact.get("end", filed_raw)
                try:
                    period_end = pd.to_datetime(end_raw).date()
                except (ValueError, TypeError):
                    continue

                start_raw = fact.get("start")
                period_start: date | None = None
                if start_raw:
                    try:
                        period_start = pd.to_datetime(start_raw).date()
                    except (ValueError, TypeError):
                        period_start = None

                if not self._is_period_acceptable(metric_name, form, period_start, period_end):
                    continue

                val = fact.get("val")
                try:
                    num_val = float(val)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue

                key = (metric_name, period_end, filed, form)
                if key in seen:
                    continue
                seen.add(key)

                rows.append(
                    {
                        COL_DATE: filed,
                        COL_SYMBOL: symbol,
                        COL_METRIC_NAME: metric_name,
                        COL_VALUE: num_val,
                        COL_FILING_TYPE: form,
                        COL_PERIOD_END: period_end,
                    }
                )

        return rows

    # ── Public surface ───────────────────────────────────────────────────

    def fetch(self, symbols: list[str], start_date: date, end_date: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Fetch fundamental data for symbols via the companyfacts API.

        Returns a DataFrame in long format with columns:
        ``date, symbol, metric_name, value, filing_type, period_end``.

        Errors for individual symbols are recorded in diagnostics but do
        not halt the batch — other symbols' data is still returned.
        """
        diag = Diagnostics()
        all_rows: list[dict[str, Any]] = []

        diag.info(
            _SRC,
            f"Fetching EDGAR companyfacts for {len(symbols)} symbols ({start_date} to {end_date})",
            symbol_count=len(symbols),
        )

        for sym in symbols:
            try:
                cik = self._resolve_cik(sym, diag)
                if cik is None:
                    diag.warning(
                        _SRC,
                        f"No CIK for symbol {sym} — skipping",
                        symbol=sym,
                    )
                    continue
                cf_data = self._fetch_companyfacts(cik, diag)
                rows = self._parse_companyfacts(
                    cf_data,
                    sym,
                    start_date,
                    end_date,
                    self._config.filing_types,
                    diag,
                )
                all_rows.extend(rows)
                diag.debug(
                    _SRC,
                    f"{sym}: extracted {len(rows)} metric rows",
                    symbol=sym,
                    row_count=len(rows),
                )
            except Exception as exc:
                diag.error(
                    _SRC,
                    f"Failed companyfacts fetch for {sym}: {exc}",
                    symbol=sym,
                )

        if not all_rows:
            diag.info(_SRC, "No EDGAR data extracted")
            return pd.DataFrame(columns=_OUTPUT_COLS), diag

        df = pd.DataFrame(all_rows)
        diag.info(
            _SRC,
            f"Extracted {len(df)} metric rows from EDGAR companyfacts",
            row_count=len(df),
        )
        return df[_OUTPUT_COLS], diag

    def fetch_incremental(self, symbols: list[str], since: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Incremental fetch for filings published since *since*."""
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
        """Check if the EDGAR API is reachable."""
        diag = Diagnostics()
        try:
            resp = self._session.get(self._config.base_url, timeout=10)
            healthy = resp.status_code < 500
            if healthy:
                diag.info(_SRC, "EDGAR API health check passed")
            else:
                diag.error(
                    _SRC,
                    f"EDGAR API returned status {resp.status_code}",
                )
            return healthy, diag
        except Exception as exc:
            diag.error(_SRC, f"EDGAR health check failed: {exc}")
            return False, diag
