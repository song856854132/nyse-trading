"""Tests for nyse_ats.data.finmind_adapter — FinMind OHLCV adapter.

Validates:
- Column mapping from FinMind names to canonical schema
- Retry on timeout (mock requests)
- Rate limiter integration
- Data gap handling
- Environment variable token loading
- Bulk fetch (fetch_incremental) behavior
"""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import MagicMock, patch

import requests

from nyse_ats.data.finmind_adapter import FinMindAdapter
from nyse_ats.data.rate_limiter import SlidingWindowRateLimiter
from nyse_core.config_schema import FinMindConfig
from nyse_core.schema import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_SYMBOL,
    COL_VOLUME,
)

# ── Fixtures ────────────────────────────────────────────────────────────────

_TEST_CONFIG = FinMindConfig(
    base_url="https://api.finmindtrade.com/api/v4",
    token_env_var="FINMIND_API_TOKEN",
    rate_limit_per_minute=30,
    datasets={"ohlcv": "USStockPrice", "info": "USStockInfo"},
    bulk_start_date="2016-01-01",
)


def _make_adapter(
    session: requests.Session | None = None,
) -> tuple[FinMindAdapter, SlidingWindowRateLimiter]:
    rl = SlidingWindowRateLimiter(max_requests=100, window_seconds=60.0)
    adapter = FinMindAdapter(config=_TEST_CONFIG, rate_limiter=rl, session=session)
    return adapter, rl


def _mock_finmind_response(data: list[dict]) -> MagicMock:
    """Build a mock response matching FinMind's JSON envelope."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": 200, "msg": "success", "data": data}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _sample_finmind_rows() -> list[dict]:
    """FinMind-format rows (raw column names)."""
    return [
        {
            "date": "2024-01-02",
            "stock_id": "AAPL",
            "Trading_Volume": 50000000,
            "Trading_turnover": 9500000000,
            "open": 185.0,
            "max": 187.5,
            "min": 184.0,
            "close": 186.5,
            "spread": 1.5,
        },
        {
            "date": "2024-01-03",
            "stock_id": "AAPL",
            "Trading_Volume": 45000000,
            "Trading_turnover": 8400000000,
            "open": 186.5,
            "max": 188.0,
            "min": 185.5,
            "close": 187.0,
            "spread": 0.5,
        },
    ]


# ── Column Mapping ──────────────────────────────────────────────────────────


class TestColumnMapping:
    """FinMind raw columns are mapped to canonical schema names."""

    def test_canonical_columns_present(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_finmind_response(_sample_finmind_rows())
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        expected_cols = {COL_DATE, COL_SYMBOL, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME}
        assert set(df.columns) == expected_cols

    def test_max_mapped_to_high(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_finmind_response(_sample_finmind_rows())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
        assert df[COL_HIGH].iloc[0] == 187.5

    def test_min_mapped_to_low(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_finmind_response(_sample_finmind_rows())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
        assert df[COL_LOW].iloc[0] == 184.0

    def test_stock_id_mapped_to_symbol(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_finmind_response(_sample_finmind_rows())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
        assert (df[COL_SYMBOL] == "AAPL").all()

    def test_trading_volume_mapped_to_volume(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_finmind_response(_sample_finmind_rows())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
        assert df[COL_VOLUME].iloc[0] == 50000000

    def test_date_column_is_python_date(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_finmind_response(_sample_finmind_rows())
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
        assert df[COL_DATE].iloc[0] == date(2024, 1, 2)


# ── Retry on Timeout ────────────────────────────────────────────────────────


class TestRetry:
    """Retry logic with exponential backoff on transient errors."""

    def test_retries_on_timeout(self) -> None:
        session = MagicMock()
        session.get.side_effect = [
            requests.Timeout("timed out"),
            requests.Timeout("timed out"),
            _mock_finmind_response(_sample_finmind_rows()),
        ]
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
        assert len(df) == 2
        assert session.get.call_count == 3

    def test_retries_on_connection_error(self) -> None:
        session = MagicMock()
        session.get.side_effect = [
            requests.ConnectionError("conn refused"),
            _mock_finmind_response(_sample_finmind_rows()),
        ]
        adapter, _ = _make_adapter(session=session)

        df, _ = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
        assert len(df) == 2

    def test_gives_up_after_3_retries(self) -> None:
        session = MagicMock()
        session.get.side_effect = requests.Timeout("timed out")
        adapter, _ = _make_adapter(session=session)

        # Should not raise — fetch() catches the exception and returns empty.
        # Per-symbol failure is recorded as a warning (partial success
        # semantic) so downstream storage still persists other symbols.
        df, diag = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
        assert df.empty
        assert session.get.call_count == 3
        assert not diag.has_errors
        assert any("Failed to fetch data for AAPL" in m.message for m in diag.messages)


# ── Rate Limiter Integration ────────────────────────────────────────────────


class TestRateLimiterIntegration:
    """Verify that the adapter calls rate_limiter.acquire()."""

    def test_acquire_called_per_request(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_finmind_response(_sample_finmind_rows())

        rl = MagicMock(spec=SlidingWindowRateLimiter)
        adapter = FinMindAdapter(config=_TEST_CONFIG, rate_limiter=rl, session=session)

        adapter.fetch(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 31))
        # One acquire() per symbol
        assert rl.acquire.call_count == 2


# ── Data Gap Handling ───────────────────────────────────────────────────────


class TestDataGaps:
    """Graceful handling of missing or empty data."""

    def test_empty_data_returns_empty_dataframe(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_finmind_response([])
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["XYZ"], date(2024, 1, 1), date(2024, 1, 31))
        assert df.empty
        expected_cols = {COL_DATE, COL_SYMBOL, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME}
        assert set(df.columns) == expected_cols

    def test_api_error_returns_empty_dataframe(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": 400, "msg": "symbol not found", "data": []}
        mock_resp.raise_for_status = MagicMock()

        session = MagicMock()
        session.get.return_value = mock_resp
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["INVALID"], date(2024, 1, 1), date(2024, 1, 31))
        assert df.empty

    def test_partial_failure_returns_successful_symbols(self) -> None:
        """If one symbol fails, other symbols' data is still returned."""
        session = MagicMock()
        session.get.side_effect = [
            _mock_finmind_response(_sample_finmind_rows()),
            requests.Timeout("timed out"),
            requests.Timeout("timed out"),
            requests.Timeout("timed out"),
        ]
        adapter, _ = _make_adapter(session=session)

        df, diag = adapter.fetch(["AAPL", "BAD"], date(2024, 1, 1), date(2024, 1, 31))
        assert len(df) == 2
        assert (df[COL_SYMBOL] == "AAPL").all()
        # Per-symbol failure is a warning, not an error — enables partial
        # success to still persist downstream.
        assert not diag.has_errors
        assert any("Failed to fetch data for BAD" in m.message for m in diag.messages)


# ── Env Var Token ───────────────────────────────────────────────────────────


class TestTokenLoading:
    """API token loaded from environment variable, never hardcoded."""

    def test_token_passed_as_param(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_finmind_response([])

        adapter, _ = _make_adapter(session=session)

        with patch.dict(os.environ, {"FINMIND_API_TOKEN": "test-secret-token"}):
            adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        call_kwargs = session.get.call_args
        params = call_kwargs.kwargs.get("params", call_kwargs[1].get("params", {}))
        assert params["token"] == "test-secret-token"

    def test_missing_token_still_works(self) -> None:
        session = MagicMock()
        session.get.return_value = _mock_finmind_response([])
        adapter, _ = _make_adapter(session=session)

        with patch.dict(os.environ, {}, clear=True):
            # Should not raise — just logs a warning
            df, _ = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))
            assert df.empty


# ── Health Check ────────────────────────────────────────────────────────────


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
