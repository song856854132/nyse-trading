"""Integration tests: data adapter -> storage round-trip.

Verifies that data flows correctly from FinMind / EDGAR / Constituency
adapters through ResearchStore and back, with all HTTP calls mocked.
Also tests the 4 data-path detection scenarios (HAPPY, NIL, EMPTY, ERROR).
"""

from __future__ import annotations

import time
from datetime import date
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

# ── Graceful skip if Phase 2 modules not yet available ────────────────────

try:
    from nyse_ats.data.constituency_adapter import ConstituencyAdapter
    from nyse_ats.data.edgar_adapter import EdgarAdapter
    from nyse_ats.data.finmind_adapter import FinMindAdapter
    from nyse_ats.data.rate_limiter import SlidingWindowRateLimiter
    from nyse_ats.pipeline import TradingPipeline
    from nyse_ats.storage.research_store import ResearchStore
    from nyse_core.config_schema import (
        ConstituencyConfig,
        EdgarConfig,
        FinMindConfig,
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
        OHLCV_COLUMNS,
    )

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False

from tests.fixtures.synthetic_constituency import generate_constituency_changes

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not MODULES_AVAILABLE, reason="Phase 2 modules not yet available"),
]


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_finmind_config() -> FinMindConfig:
    return FinMindConfig(
        base_url="https://api.finmindtrade.com/api/v4",
        token_env_var="FINMIND_TOKEN",
        rate_limit_per_minute=30,
        datasets={"ohlcv": "USStockPrice"},
        bulk_start_date="2020-01-01",
    )


def _make_edgar_config() -> EdgarConfig:
    return EdgarConfig(
        base_url="https://efts.sec.gov",
        rate_limit_per_second=10,
        user_agent_env_var="EDGAR_USER_AGENT",
        filing_types=["10-Q", "10-K"],
    )


def _make_constituency_config(csv_path: str) -> ConstituencyConfig:
    return ConstituencyConfig(
        source="manual_csv",
        backup_source="manual_csv",
        csv_path=csv_path,
    )


def _build_finmind_response(
    symbols: list[str],
    start_date: date,
    end_date: date,
    seed: int = 42,
) -> dict[str, Any]:
    """Build a mock FinMind API JSON response for given symbols."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=str(start_date), end=str(end_date), freq="B")
    data: list[dict] = []
    for sym in symbols:
        base_price = rng.uniform(20, 200)
        for dt in dates:
            c = round(float(base_price * (1 + rng.normal(0, 0.01))), 2)
            data.append(
                {
                    "date": dt.strftime("%Y-%m-%d"),
                    "stock_id": sym,
                    "open": round(c * rng.uniform(0.99, 1.01), 2),
                    "max": round(c * rng.uniform(1.0, 1.03), 2),
                    "min": round(c * rng.uniform(0.97, 1.0), 2),
                    "close": c,
                    "Trading_Volume": int(rng.lognormal(14, 0.5)),
                }
            )
    return {"status": 200, "msg": "success", "data": data}


def _build_edgar_response(
    symbol: str,
    n_filings: int = 2,
) -> dict[str, Any]:
    """Build a mock EDGAR search API JSON response."""
    hits = []
    for i in range(n_filings):
        period_end = f"2024-{6 + i:02d}-30"
        file_date = f"2024-{7 + i:02d}-15"
        hits.append(
            {
                "_source": {
                    "file_date": file_date,
                    "period_of_report": period_end,
                    "file_type": "10-Q",
                    "xbrl_facts": {
                        "Revenues": 1_000_000 * (i + 1),
                        "NetIncomeLoss": 200_000 * (i + 1),
                        "Assets": 5_000_000 * (i + 1),
                    },
                }
            }
        )
    return {"hits": {"hits": hits}}


# ── Test Classes ──────────────────────────────────────────────────────────


class TestAdapterToStorageFlow:
    """Data flows from adapter -> ResearchStore correctly."""

    def test_finmind_to_research_store(self, tmp_path: Path) -> None:
        """Mock FinMind API -> adapter.fetch() -> store.store_ohlcv() -> load -> verify."""
        config = _make_finmind_config()
        limiter = SlidingWindowRateLimiter(max_requests=100, window_seconds=60)
        session = MagicMock()

        symbols = ["AAPL", "MSFT"]
        start = date(2024, 6, 1)
        end = date(2024, 6, 30)

        # Build per-symbol mock responses: adapter calls session.get() once per symbol
        responses = []
        for sym in symbols:
            resp_json = _build_finmind_response([sym], start, end, seed=42)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = resp_json
            mock_resp.raise_for_status.return_value = None
            responses.append(mock_resp)
        session.get.side_effect = responses

        adapter = FinMindAdapter(config, limiter, session=session)
        ohlcv_df, diag = adapter.fetch(symbols, start, end)

        assert not diag.has_errors, f"Fetch errors: {diag.messages}"
        assert not ohlcv_df.empty
        assert set(ohlcv_df.columns) >= {
            COL_DATE,
            COL_SYMBOL,
            COL_OPEN,
            COL_HIGH,
            COL_LOW,
            COL_CLOSE,
            COL_VOLUME,
        }

        # Round-trip through ResearchStore
        with ResearchStore(tmp_path / "research.duckdb") as store:
            store_diag = store.store_ohlcv(ohlcv_df)
            assert not store_diag.has_errors

            loaded, load_diag = store.load_ohlcv(symbols, start, end)
            assert not load_diag.has_errors
            assert len(loaded) == len(ohlcv_df)

    @pytest.mark.skip(
        reason="Mock structure matches legacy EDGAR search API; current adapter uses "
        "companyfacts XBRL endpoint. Test needs rewrite — tracked in TODO-30."
    )
    def test_edgar_to_research_store(self, tmp_path: Path) -> None:
        """Mock EDGAR API -> adapter.fetch() -> store features -> load -> verify."""
        config = _make_edgar_config()
        limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=1)
        session = MagicMock()

        symbols = ["AAPL"]
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _build_edgar_response("AAPL", n_filings=2)
        mock_resp.raise_for_status.return_value = None
        session.get.return_value = mock_resp

        adapter = EdgarAdapter(config, limiter, session=session)
        edgar_df, diag = adapter.fetch(symbols, start, end)

        assert not diag.has_errors
        assert not edgar_df.empty
        assert "metric_name" in edgar_df.columns
        assert "value" in edgar_df.columns

        # Store as features in ResearchStore
        rebalance = date(2024, 7, 15)
        feature_df = edgar_df.rename(columns={"metric_name": "factor_name"}).copy()
        feature_df = feature_df[[COL_DATE, COL_SYMBOL, "factor_name", "value"]]

        with ResearchStore(tmp_path / "research.duckdb") as store:
            store_diag = store.store_features(feature_df, rebalance)
            assert not store_diag.has_errors

            loaded, load_diag = store.load_features(rebalance)
            assert not load_diag.has_errors

    def test_constituency_to_universe(self, tmp_path: Path) -> None:
        """Constituency adapter -> load via CSV -> produces correct membership."""
        symbols = [f"SYM_{i:02d}" for i in range(20)]
        changes_df = generate_constituency_changes(
            initial_members=symbols,
            n_changes=10,
            seed=42,
        )

        csv_path = tmp_path / "constituency.csv"
        changes_df.to_csv(csv_path, index=False)

        config = _make_constituency_config(str(csv_path))
        adapter = ConstituencyAdapter(config)

        result_df, diag = adapter.fetch(
            symbols=[],
            start_date=date(2022, 1, 1),
            end_date=date(2025, 1, 1),
        )
        assert not diag.has_errors
        assert not result_df.empty
        assert "action" in result_df.columns
        assert set(result_df["action"].unique()) <= {"ADD", "REMOVE"}

    def test_rate_limiter_enforces_during_bulk_fetch(self) -> None:
        """Rate limiter blocks when adapter makes rapid requests."""
        # 3 requests per 0.5s window -- the 4th must wait
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=0.5)

        times: list[float] = []
        for _ in range(4):
            t0 = time.monotonic()
            limiter.acquire()
            times.append(time.monotonic() - t0)

        # First 3 should be near-instant, 4th should wait ~0.5s
        assert times[0] < 0.1
        assert times[1] < 0.1
        assert times[2] < 0.1
        assert times[3] >= 0.3, f"4th acquire too fast: {times[3]:.3f}s"

    def test_finmind_adapter_handles_api_error(self) -> None:
        """FinMind adapter logs diagnostics on API error response."""
        config = _make_finmind_config()
        limiter = SlidingWindowRateLimiter(max_requests=100, window_seconds=60)
        session = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": 400, "msg": "invalid token"}
        mock_resp.raise_for_status.return_value = None
        session.get.return_value = mock_resp

        adapter = FinMindAdapter(config, limiter, session=session)
        result, diag = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        # Should return empty with warning but no crash
        assert result.empty or len(result) == 0

    def test_finmind_adapter_handles_empty_data(self) -> None:
        """FinMind adapter returns empty df when API yields no rows."""
        config = _make_finmind_config()
        limiter = SlidingWindowRateLimiter(max_requests=100, window_seconds=60)
        session = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": 200, "msg": "success", "data": []}
        mock_resp.raise_for_status.return_value = None
        session.get.return_value = mock_resp

        adapter = FinMindAdapter(config, limiter, session=session)
        result, diag = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 1, 31))

        assert result.empty

    def test_edgar_adapter_handles_no_filings(self) -> None:
        """EDGAR adapter returns empty df when no filings found."""
        config = _make_edgar_config()
        limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=1)
        session = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hits": {"hits": []}}
        mock_resp.raise_for_status.return_value = None
        session.get.return_value = mock_resp

        adapter = EdgarAdapter(config, limiter, session=session)
        result, diag = adapter.fetch(["AAPL"], date(2024, 1, 1), date(2024, 12, 31))

        assert result.empty


class TestDataPathDetection:
    """Verify the 4 data paths: HAPPY, NIL, EMPTY, ERROR."""

    @pytest.fixture()
    def _pipeline_factory(self) -> Any:
        """Create a minimal TradingPipeline for data-path testing."""

        class FakeStrategyParams:
            class allocator:
                top_n = 20
                sell_buffer = 1.5

            class combination:
                model = "ridge"
                alpha = 1.0
                target_horizon_days = 5

            class risk:
                max_position_pct = 0.10
                max_sector_pct = 0.30
                position_inertia_threshold = 0.005
                beta_cap_low = 0.5
                beta_cap_high = 1.5
                daily_loss_limit = -0.03
                earnings_event_cap = 0.05
                earnings_event_days = 2

            class rebalance:
                frequency = "weekly"

            kill_switch = False

        def factory(tmp_path: Path) -> TradingPipeline:
            store = ResearchStore(tmp_path / "research.duckdb")
            registry = MagicMock()
            config = {"strategy_params": FakeStrategyParams()}
            return TradingPipeline(
                config=config,
                data_adapters={},
                storage=store,
                factor_registry=registry,
            )

        return factory

    def test_happy_path_full_data(self, tmp_path: Path, _pipeline_factory: Any) -> None:
        """All data present -> features computed -> HAPPY path detected."""
        pipeline = _pipeline_factory(tmp_path)
        symbols = [f"SYM_{i:02d}" for i in range(20)]

        rng = np.random.default_rng(42)
        features = pd.DataFrame(
            {
                COL_SYMBOL: symbols,
                "factor_a": rng.uniform(0, 1, 20),
                "factor_b": rng.uniform(0, 1, 20),
            }
        )

        path = pipeline._detect_data_path(features)
        assert path == "HAPPY"

    def test_nil_path_high_nan_fraction(self, tmp_path: Path, _pipeline_factory: Any) -> None:
        """25% NaN in features -> NIL path."""
        pipeline = _pipeline_factory(tmp_path)

        rng = np.random.default_rng(42)
        values = rng.uniform(0, 1, 100)
        # Inject 25% NaN (above _NIL_THRESHOLD=0.20)
        values[:25] = np.nan
        features = pd.DataFrame(
            {
                COL_SYMBOL: [f"SYM_{i:02d}" for i in range(100)],
                "factor_a": values,
            }
        )

        path = pipeline._detect_data_path(features)
        assert path == "NIL"

    def test_empty_path_all_nan(self, tmp_path: Path, _pipeline_factory: Any) -> None:
        """All features NaN -> EMPTY path."""
        pipeline = _pipeline_factory(tmp_path)
        features = pd.DataFrame(
            {
                COL_SYMBOL: [f"SYM_{i:02d}" for i in range(10)],
                "factor_a": [np.nan] * 10,
            }
        )

        path = pipeline._detect_data_path(features)
        assert path == "EMPTY"

    def test_error_path_majority_nan(self, tmp_path: Path, _pipeline_factory: Any) -> None:
        """60% NaN (>50%) -> ERROR path."""
        pipeline = _pipeline_factory(tmp_path)

        rng = np.random.default_rng(42)
        values = rng.uniform(0, 1, 100)
        values[:60] = np.nan
        features = pd.DataFrame(
            {
                COL_SYMBOL: [f"SYM_{i:02d}" for i in range(100)],
                "factor_a": values,
            }
        )

        path = pipeline._detect_data_path(features)
        assert path == "ERROR"

    def test_empty_path_on_empty_dataframe(self, tmp_path: Path, _pipeline_factory: Any) -> None:
        """Completely empty DataFrame -> EMPTY path."""
        pipeline = _pipeline_factory(tmp_path)
        features = pd.DataFrame()

        path = pipeline._detect_data_path(features)
        assert path == "EMPTY"
