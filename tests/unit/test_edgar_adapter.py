"""Tests for nyse_ats.data.edgar_adapter — SEC EDGAR companyfacts adapter.

Validates:
- Companyfacts JSON parsed into long-format fact rows
- Period-length disambiguation (quarterly vs annual vs YTD)
- Unit selection (USD vs shares vs USD/shares)
- Tag-precedence dedup: first ``_XBRL_TAG_MAP`` tag for a metric wins
- CIK resolution (injected map and lazy fetch)
- 404 (no companyfacts document) is tolerated
- Rate limiter acquired once per HTTP call
- User-Agent sourced from env var
"""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import MagicMock, patch

import requests

from nyse_ats.data.edgar_adapter import (
    COL_FILING_TYPE,
    COL_METRIC_NAME,
    COL_PERIOD_END,
    COL_VALUE,
    EdgarAdapter,
)
from nyse_ats.data.rate_limiter import SlidingWindowRateLimiter
from nyse_core.config_schema import EdgarConfig
from nyse_core.schema import COL_DATE, COL_SYMBOL

# ── Fixtures ────────────────────────────────────────────────────────────────

_TEST_CONFIG = EdgarConfig(
    base_url="https://data.sec.gov",
    rate_limit_per_second=10,
    user_agent_env_var="EDGAR_USER_AGENT",
    filing_types=["10-Q", "10-K"],
)

_TICKER_MAP = {"AAPL": 320193, "MSFT": 789019, "GOOG": 1652044}


def _make_adapter(
    session: requests.Session | None = None,
    ticker_cik_map: dict[str, int] | None = None,
    rate_limiter: SlidingWindowRateLimiter | None = None,
) -> tuple[EdgarAdapter, SlidingWindowRateLimiter]:
    rl = rate_limiter or SlidingWindowRateLimiter(max_requests=100, window_seconds=1.0)
    with patch.dict(os.environ, {"EDGAR_USER_AGENT": "TestBot test@example.com"}):
        adapter = EdgarAdapter(
            config=_TEST_CONFIG,
            rate_limiter=rl,
            session=session,
            ticker_cik_map=ticker_cik_map or _TICKER_MAP,
        )
    return adapter, rl


def _mock_json_response(payload: dict, status: int = 200) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_404_response() -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _companyfacts(
    *,
    revenue_quarterly: float | None = 81_797_000_000,
    revenue_annual: float | None = 383_285_000_000,
    revenue_ytd: float | None = 293_792_000_000,
    net_income: float | None = 33_916_000_000,
    assets: float | None = 352_583_000_000,
    operating_cf: float | None = 39_895_000_000,
    shares_out: float | None = 15_500_000_000,
    filed_q: str = "2024-02-02",
    filed_k: str = "2023-11-03",
    end_q: str = "2023-12-30",
    start_q: str = "2023-09-30",
    end_k: str = "2023-09-30",
    start_k: str = "2022-10-01",
) -> dict:
    """Build a minimal companyfacts JSON payload for Apple-like facts.

    Includes one quarterly Revenues row, one annual Revenues row, and one
    YTD Revenues row to exercise period-length disambiguation.
    """
    units_rev_usd: list[dict] = []
    if revenue_quarterly is not None:
        units_rev_usd.append(
            {
                "form": "10-Q",
                "filed": filed_q,
                "end": end_q,
                "start": start_q,
                "val": revenue_quarterly,
                "fp": "Q1",
            }
        )
    if revenue_annual is not None:
        units_rev_usd.append(
            {
                "form": "10-K",
                "filed": filed_k,
                "end": end_k,
                "start": start_k,
                "val": revenue_annual,
                "fp": "FY",
            }
        )
    if revenue_ytd is not None:
        # YTD rollup (9 months ~ 270d) — must be discarded by period filter
        units_rev_usd.append(
            {
                "form": "10-Q",
                "filed": filed_q,
                "end": end_q,
                "start": "2023-04-01",
                "val": revenue_ytd,
                "fp": "Q3",
            }
        )

    facts: dict[str, dict] = {}
    if units_rev_usd:
        facts["Revenues"] = {"units": {"USD": units_rev_usd}}
    if net_income is not None:
        facts["NetIncomeLoss"] = {
            "units": {
                "USD": [
                    {
                        "form": "10-Q",
                        "filed": filed_q,
                        "end": end_q,
                        "start": start_q,
                        "val": net_income,
                    }
                ]
            }
        }
    if assets is not None:
        # Balance-sheet (no start)
        facts["Assets"] = {
            "units": {
                "USD": [
                    {
                        "form": "10-Q",
                        "filed": filed_q,
                        "end": end_q,
                        "val": assets,
                    }
                ]
            }
        }
    if operating_cf is not None:
        facts["NetCashProvidedByUsedInOperatingActivities"] = {
            "units": {
                "USD": [
                    {
                        "form": "10-Q",
                        "filed": filed_q,
                        "end": end_q,
                        "start": start_q,
                        "val": operating_cf,
                    }
                ]
            }
        }
    if shares_out is not None:
        facts["CommonStockSharesOutstanding"] = {
            "units": {
                "shares": [
                    {
                        "form": "10-Q",
                        "filed": filed_q,
                        "end": end_q,
                        "val": shares_out,
                    }
                ]
            }
        }

    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {"us-gaap": facts},
    }


# ── Companyfacts parse success ──────────────────────────────────────────────


class TestCompanyfactsParseSuccess:
    """Well-formed companyfacts JSON produces correct long-format rows."""

    def test_extracts_metrics_in_long_format(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_json_response(_companyfacts())
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))

        assert not df.empty
        assert set(df.columns) == {
            COL_DATE,
            COL_SYMBOL,
            COL_METRIC_NAME,
            COL_VALUE,
            COL_FILING_TYPE,
            COL_PERIOD_END,
        }
        # Expected metrics present
        metrics = set(df[COL_METRIC_NAME].unique())
        assert "revenue" in metrics
        assert "net_income" in metrics
        assert "total_assets" in metrics
        assert "operating_cash_flow" in metrics
        assert "shares_outstanding" in metrics

    def test_revenue_quarterly_and_annual_kept_ytd_dropped(self) -> None:
        """Period-length filter keeps 10-Q quarterly + 10-K annual, drops YTD."""
        session = MagicMock()
        session.get.return_value = _mock_json_response(_companyfacts())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        rev_rows = df[df[COL_METRIC_NAME] == "revenue"]

        # Should see exactly two revenue rows: the quarterly + annual
        # (YTD 9-month rollup is 273d, outside both 80-100 and 350-380 bands)
        assert len(rev_rows) == 2
        vals = set(rev_rows[COL_VALUE].tolist())
        assert 81_797_000_000 in vals
        assert 383_285_000_000 in vals
        assert 293_792_000_000 not in vals

    def test_filed_date_and_symbol_populated(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_json_response(_companyfacts())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        assert (df[COL_SYMBOL] == "AAPL").all()
        # filed date is in [filed_q, filed_k]
        filed_dates = set(df[COL_DATE].tolist())
        assert date(2024, 2, 2) in filed_dates
        assert date(2023, 11, 3) in filed_dates

    def test_balance_sheet_metric_no_period_start_accepted(self) -> None:
        """Assets has no 'start' field but should still be kept (PiT metric)."""
        session = MagicMock()
        session.get.return_value = _mock_json_response(_companyfacts())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        assets_rows = df[df[COL_METRIC_NAME] == "total_assets"]
        assert len(assets_rows) == 1
        assert assets_rows[COL_VALUE].iloc[0] == 352_583_000_000

    def test_shares_outstanding_selected_from_shares_unit(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_json_response(_companyfacts())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        shares_rows = df[df[COL_METRIC_NAME] == "shares_outstanding"]
        assert len(shares_rows) == 1
        assert shares_rows[COL_VALUE].iloc[0] == 15_500_000_000

    def test_tag_precedence_first_wins(self) -> None:
        """If both ``Revenues`` and ``SalesRevenueNet`` present for same
        (period_end, filed, form), the first tag in _XBRL_TAG_MAP wins."""
        cf = _companyfacts(revenue_ytd=None)
        # Add a second revenue-like tag for the same quarterly slot
        cf["facts"]["us-gaap"]["SalesRevenueNet"] = {
            "units": {
                "USD": [
                    {
                        "form": "10-Q",
                        "filed": "2024-02-02",
                        "end": "2023-12-30",
                        "start": "2023-09-30",
                        "val": 99_999,
                    }
                ]
            }
        }
        session = MagicMock()
        session.get.return_value = _mock_json_response(cf)
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        q_rows = df[(df[COL_METRIC_NAME] == "revenue") & (df[COL_FILING_TYPE] == "10-Q")]
        # First tag (Revenues) wins; SalesRevenueNet dropped for same slot
        assert (q_rows[COL_VALUE] == 81_797_000_000).all()

    def test_filed_outside_window_is_dropped(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_json_response(_companyfacts())
        adapter, _ = _make_adapter(session=session)

        # Request a window that excludes both 2023-11-03 and 2024-02-02
        df, _ = adapter.fetch(["AAPL"], date(2020, 1, 1), date(2020, 12, 31))
        assert df.empty


# ── Companyfacts parse failure modes ───────────────────────────────────────


class TestCompanyfactsFailureModes:
    def test_404_returns_empty(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_404_response()
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        assert df.empty
        # 404 surfaces as warning, not error
        assert not diag.has_errors

    def test_missing_us_gaap_returns_empty_with_warning(self) -> None:
        payload = {"cik": 1, "entityName": "X", "facts": {}}
        session = MagicMock()
        session.get.return_value = _mock_json_response(payload)
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        assert df.empty
        warnings = [m for m in diag.messages if m.level.value == "WARNING"]
        assert any("no us-gaap" in m.message.lower() for m in warnings)

    def test_unknown_ticker_skipped_with_warning(self) -> None:
        session = MagicMock()
        adapter, _ = _make_adapter(session=session, ticker_cik_map=_TICKER_MAP)

        df, diag = adapter.fetch(["UNKNOWN"], date(2023, 1, 1), date(2024, 12, 31))
        assert df.empty
        # No HTTP call issued because CIK resolution failed
        session.get.assert_not_called()
        warnings = [m for m in diag.messages if m.level.value == "WARNING"]
        assert any("UNKNOWN" in m.message for m in warnings)

    def test_partial_facts(self) -> None:
        """Only revenue present in companyfacts → only revenue rows."""
        cf = _companyfacts(
            net_income=None,
            assets=None,
            operating_cf=None,
            shares_out=None,
            revenue_ytd=None,
            revenue_annual=None,
        )
        session = MagicMock()
        session.get.return_value = _mock_json_response(cf)
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        assert len(df) == 1
        assert df[COL_METRIC_NAME].iloc[0] == "revenue"

    def test_non_numeric_val_skipped(self) -> None:
        cf = _companyfacts(revenue_ytd=None, revenue_annual=None)
        cf["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0]["val"] = None
        session = MagicMock()
        session.get.return_value = _mock_json_response(cf)
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        assert df[df[COL_METRIC_NAME] == "revenue"].empty

    def test_malformed_filed_date_skipped(self) -> None:
        cf = _companyfacts(revenue_ytd=None, revenue_annual=None)
        cf["facts"]["us-gaap"]["Revenues"]["units"]["USD"][0]["filed"] = "not-a-date"
        session = MagicMock()
        session.get.return_value = _mock_json_response(cf)
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        assert df[df[COL_METRIC_NAME] == "revenue"].empty


# ── Filing-type filter ─────────────────────────────────────────────────────


class TestFilingTypeFilter:
    def test_non_10q_10k_forms_dropped(self) -> None:
        cf = _companyfacts(revenue_ytd=None, revenue_annual=None)
        # Inject an 8-K row — should be filtered out
        cf["facts"]["us-gaap"]["Revenues"]["units"]["USD"].append(
            {
                "form": "8-K",
                "filed": "2024-02-15",
                "end": "2023-12-30",
                "start": "2023-09-30",
                "val": 77_777,
            }
        )
        session = MagicMock()
        session.get.return_value = _mock_json_response(cf)
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        assert 77_777 not in set(df[COL_VALUE].tolist())


# ── CIK resolution ─────────────────────────────────────────────────────────


class TestCikResolution:
    def test_injected_map_skips_ticker_fetch(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_json_response(_companyfacts())
        adapter, _ = _make_adapter(session=session, ticker_cik_map={"AAPL": 320193})

        adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        # Exactly one GET: the companyfacts call. No ticker-map round-trip.
        assert session.get.call_count == 1
        url = session.get.call_args.args[0]
        assert "companyfacts/CIK0000320193.json" in url

    def test_lazy_fetch_ticker_map_when_missing(self) -> None:
        ticker_payload = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        }
        session = MagicMock()
        # First call = ticker map; second = companyfacts
        session.get.side_effect = [
            _mock_json_response(ticker_payload),
            _mock_json_response(_companyfacts()),
        ]

        rl = SlidingWindowRateLimiter(max_requests=100, window_seconds=1.0)
        with patch.dict(os.environ, {"EDGAR_USER_AGENT": "TestBot test@example.com"}):
            adapter = EdgarAdapter(
                config=_TEST_CONFIG,
                rate_limiter=rl,
                session=session,
                ticker_cik_map=None,
            )

        df, _ = adapter.fetch(["AAPL"], date(2023, 1, 1), date(2024, 12, 31))
        assert session.get.call_count == 2
        assert not df.empty


# ── Rate limit ─────────────────────────────────────────────────────────────


class TestRateLimit:
    def test_acquire_called_per_http_request(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_json_response(_companyfacts())

        rl = MagicMock(spec=SlidingWindowRateLimiter)
        with patch.dict(os.environ, {"EDGAR_USER_AGENT": "TestBot test@example.com"}):
            adapter = EdgarAdapter(
                config=_TEST_CONFIG,
                rate_limiter=rl,
                session=session,
                ticker_cik_map=_TICKER_MAP,
            )

        adapter.fetch(["AAPL", "MSFT", "GOOG"], date(2023, 1, 1), date(2024, 12, 31))
        # One acquire per companyfacts call (3 symbols → 3 calls)
        assert rl.acquire.call_count == 3


# ── User-Agent header ──────────────────────────────────────────────────────


class TestUserAgent:
    def test_user_agent_set_from_env(self) -> None:
        session = MagicMock()
        session.headers = {}

        with patch.dict(os.environ, {"EDGAR_USER_AGENT": "MyBot admin@company.com"}):
            EdgarAdapter(
                config=_TEST_CONFIG,
                rate_limiter=SlidingWindowRateLimiter(max_requests=100, window_seconds=1.0),
                session=session,
                ticker_cik_map=_TICKER_MAP,
            )

        assert session.headers["User-Agent"] == "MyBot admin@company.com"

    def test_missing_env_var_uses_fallback(self) -> None:
        session = MagicMock()
        session.headers = {}

        with patch.dict(os.environ, {}, clear=True):
            EdgarAdapter(
                config=_TEST_CONFIG,
                rate_limiter=SlidingWindowRateLimiter(max_requests=100, window_seconds=1.0),
                session=session,
                ticker_cik_map=_TICKER_MAP,
            )

        assert session.headers.get("User-Agent")


# ── Health check ───────────────────────────────────────────────────────────


class TestHealthCheck:
    def test_health_check_success(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        session.get.return_value = mock_resp
        adapter, _ = _make_adapter(session=session)

        healthy, diag = adapter.health_check()
        assert healthy is True

    def test_health_check_failure(self) -> None:
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("unreachable")
        adapter, _ = _make_adapter(session=session)

        healthy, diag = adapter.health_check()
        assert healthy is False
        assert diag.has_errors
