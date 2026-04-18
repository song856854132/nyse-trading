"""Tests for nyse_ats.data.finra_adapter -- FINRA Short Interest adapter.

Validates:
- Successful fetch parses records correctly
- Publication lag dates are computed (settlement + 11 days)
- API unavailable triggers retry logic
- Empty response handled gracefully
- Rate limiter is called
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import requests

from nyse_ats.data.finra_adapter import (
    COL_DAYS_TO_COVER,
    COL_PUBLICATION_DATE,
    COL_SHORT_INTEREST,
    COL_SHORT_RATIO,
    FinraAdapter,
)
from nyse_ats.data.rate_limiter import SlidingWindowRateLimiter
from nyse_core.config_schema import FinraConfig
from nyse_core.contracts import DiagLevel
from nyse_core.schema import COL_DATE, COL_SYMBOL

# ── Fixtures ────────────────────────────────────────────────────────────────

_TEST_CONFIG = FinraConfig(
    short_interest_url="https://api.finra.org/data/group/otcMarket/name/shortInterest",
    publication_lag_days=11,
    update_frequency="bi-monthly",
)


def _make_adapter(
    session: requests.Session | None = None,
) -> tuple[FinraAdapter, SlidingWindowRateLimiter]:
    rl = SlidingWindowRateLimiter(max_requests=100, window_seconds=1.0)
    adapter = FinraAdapter(config=_TEST_CONFIG, rate_limiter=rl, session=session)
    return adapter, rl


def _mock_finra_response(records: list[dict]) -> MagicMock:
    """Build a mock response matching FINRA API format."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = records
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _sample_records() -> list[dict]:
    """FINRA-format short interest records."""
    return [
        {
            "settlementDate": "2024-01-15",
            "symbolCode": "AAPL",
            "currentShortPositionQuantity": 120000000,
            "daysToCoverQuantity": 2.5,
            "shortInterestRatioQuantity": 0.015,
        },
        {
            "settlementDate": "2024-01-15",
            "symbolCode": "MSFT",
            "currentShortPositionQuantity": 45000000,
            "daysToCoverQuantity": 1.8,
            "shortInterestRatioQuantity": 0.008,
        },
    ]


# ── Successful Fetch ─────────────────────────────────────────────────────────


class TestSuccessfulFetch:
    """Happy-path short interest fetching."""

    def test_fetch_returns_correct_columns(self) -> None:
        session = MagicMock()
        session.post.return_value = _mock_finra_response(_sample_records())
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 31))

        assert not df.empty
        assert COL_DATE in df.columns
        assert COL_SYMBOL in df.columns
        assert COL_SHORT_INTEREST in df.columns
        assert COL_DAYS_TO_COVER in df.columns
        assert COL_SHORT_RATIO in df.columns
        assert not diag.has_errors

    def test_fetch_returns_correct_values(self) -> None:
        session = MagicMock()
        session.post.return_value = _mock_finra_response(_sample_records())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 31))

        aapl = df[df[COL_SYMBOL] == "AAPL"].iloc[0]
        assert aapl[COL_SHORT_INTEREST] == 120000000
        assert aapl[COL_DAYS_TO_COVER] == 2.5
        assert aapl[COL_SHORT_RATIO] == 0.015

    def test_fetch_returns_multiple_symbols(self) -> None:
        session = MagicMock()
        session.post.return_value = _mock_finra_response(_sample_records())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 31))

        assert len(df) == 2
        assert set(df[COL_SYMBOL]) == {"AAPL", "MSFT"}


# ── Publication Lag (PiT Rule) ───────────────────────────────────────────────


class TestPublicationLag:
    """FINRA 11-day publication lag must be correctly computed."""

    def test_settlement_date_as_date_column(self) -> None:
        """The date column must be the settlement date, not publication."""
        session = MagicMock()
        session.post.return_value = _mock_finra_response(_sample_records())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        aapl = df[df[COL_SYMBOL] == "AAPL"].iloc[0]
        assert aapl[COL_DATE] == date(2024, 1, 15)

    def test_publication_date_is_settlement_plus_lag(self) -> None:
        """publication_date = settlement_date + 11 days."""
        session = MagicMock()
        session.post.return_value = _mock_finra_response(_sample_records())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        aapl = df[df[COL_SYMBOL] == "AAPL"].iloc[0]
        expected_pub = date(2024, 1, 15) + timedelta(days=11)
        assert aapl[COL_PUBLICATION_DATE] == expected_pub

    def test_lag_uses_config_value(self) -> None:
        """The lag should come from config.publication_lag_days, not hardcoded."""
        config_7day = FinraConfig(
            short_interest_url="https://api.finra.org/data",
            publication_lag_days=7,
            update_frequency="bi-monthly",
        )
        rl = SlidingWindowRateLimiter(max_requests=100, window_seconds=1.0)
        session = MagicMock()
        session.post.return_value = _mock_finra_response(_sample_records())
        adapter = FinraAdapter(config=config_7day, rate_limiter=rl, session=session)

        df, _ = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        aapl = df[df[COL_SYMBOL] == "AAPL"].iloc[0]
        expected_pub = date(2024, 1, 15) + timedelta(days=7)
        assert aapl[COL_PUBLICATION_DATE] == expected_pub


# ── Retry on API Unavailable ─────────────────────────────────────────────────


class TestRetry:
    """Retry logic for transient API failures."""

    def test_retries_on_connection_error(self) -> None:
        session = MagicMock()
        session.post.side_effect = [
            requests.ConnectionError("connection refused"),
            _mock_finra_response(_sample_records()),
        ]
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        assert not df.empty
        assert session.post.call_count == 2

    def test_retries_on_timeout(self) -> None:
        session = MagicMock()
        session.post.side_effect = [
            requests.Timeout("timed out"),
            requests.Timeout("timed out"),
            _mock_finra_response(_sample_records()),
        ]
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        assert not df.empty
        assert session.post.call_count == 3

    def test_gives_up_after_3_retries(self) -> None:
        session = MagicMock()
        session.post.side_effect = requests.Timeout("timed out")
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        assert df.empty
        assert diag.has_errors
        assert session.post.call_count == 3


# ── Empty Response ───────────────────────────────────────────────────────────


class TestEmptyResponse:
    """Graceful handling of empty API responses."""

    def test_empty_records_list(self) -> None:
        session = MagicMock()
        session.post.return_value = _mock_finra_response([])
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        assert df.empty
        warnings = [m for m in diag.messages if m.level == DiagLevel.WARNING]
        assert any("no short interest" in m.message.lower() for m in warnings)

    def test_records_missing_settlement_date_skipped(self) -> None:
        records = [
            {
                "settlementDate": "",
                "symbolCode": "AAPL",
                "currentShortPositionQuantity": 100,
                "daysToCoverQuantity": 1.0,
                "shortInterestRatioQuantity": 0.01,
            },
        ]
        session = MagicMock()
        session.post.return_value = _mock_finra_response(records)
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        assert df.empty


# ── Rate Limiter Integration ─────────────────────────────────────────────────


class TestRateLimiterIntegration:
    """Verify that the adapter calls rate_limiter.acquire()."""

    def test_acquire_called(self) -> None:
        session = MagicMock()
        session.post.return_value = _mock_finra_response(_sample_records())

        rl = MagicMock(spec=SlidingWindowRateLimiter)
        adapter = FinraAdapter(config=_TEST_CONFIG, rate_limiter=rl, session=session)

        adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
        assert rl.acquire.call_count == 1


# ── Health Check ─────────────────────────────────────────────────────────────


class TestHealthCheck:
    def test_health_check_success(self) -> None:
        session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        session.get.return_value = mock_resp
        adapter, _ = _make_adapter(session=session)

        healthy, diag = adapter.health_check()
        assert healthy is True
        assert not diag.has_errors

    def test_health_check_failure(self) -> None:
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("down")
        adapter, _ = _make_adapter(session=session)

        healthy, diag = adapter.health_check()
        assert healthy is False
        assert diag.has_errors
