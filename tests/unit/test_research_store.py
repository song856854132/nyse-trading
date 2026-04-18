"""Unit tests for nyse_ats.storage.research_store."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from nyse_ats.storage.research_store import ResearchStore
from nyse_core.contracts import BacktestResult
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
    from pathlib import Path


@pytest.fixture
def store(tmp_path: Path) -> ResearchStore:
    """Create a ResearchStore backed by a temporary DuckDB file."""
    db_path = tmp_path / "research.duckdb"
    s = ResearchStore(db_path)
    yield s
    s.close()


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Small OHLCV DataFrame for testing."""
    return pd.DataFrame(
        {
            COL_DATE: [date(2024, 1, 2), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 3)],
            COL_SYMBOL: ["AAPL", "MSFT", "AAPL", "MSFT"],
            COL_OPEN: [150.0, 300.0, 152.0, 305.0],
            COL_HIGH: [155.0, 310.0, 158.0, 312.0],
            COL_LOW: [148.0, 298.0, 150.0, 302.0],
            COL_CLOSE: [153.0, 308.0, 156.0, 310.0],
            COL_VOLUME: [1000000, 2000000, 1100000, 2100000],
        }
    )


@pytest.fixture
def sample_features() -> pd.DataFrame:
    """Small feature DataFrame for testing."""
    return pd.DataFrame(
        {
            COL_DATE: [date(2024, 1, 2)] * 4,
            COL_SYMBOL: ["AAPL", "AAPL", "MSFT", "MSFT"],
            "factor_name": ["momentum", "value", "momentum", "value"],
            "value": [0.85, 0.40, 0.60, 0.75],
        }
    )


@pytest.fixture
def sample_fundamentals() -> pd.DataFrame:
    """Long-format XBRL facts mimicking EDGAR adapter output.

    Two filings for AAPL (10-Q + 10-K) and one for MSFT. Revenue+NI per filing.
    NaN in one value slot to exercise XBRL-parse-failure handling.
    """
    return pd.DataFrame(
        {
            COL_DATE: [
                date(2023, 5, 1),
                date(2023, 5, 1),
                date(2023, 11, 2),
                date(2023, 11, 2),
                date(2023, 7, 27),
                date(2023, 7, 27),
            ],
            COL_SYMBOL: ["AAPL", "AAPL", "AAPL", "AAPL", "MSFT", "MSFT"],
            "metric_name": [
                "revenue",
                "net_income",
                "revenue",
                "net_income",
                "revenue",
                "net_income",
            ],
            "value": [94836.0, 24160.0, 383285.0, 96995.0, 56189.0, float("nan")],
            "filing_type": ["10-Q", "10-Q", "10-K", "10-K", "10-Q", "10-Q"],
            "period_end": [
                date(2023, 4, 1),
                date(2023, 4, 1),
                date(2023, 9, 30),
                date(2023, 9, 30),
                date(2023, 6, 30),
                date(2023, 6, 30),
            ],
        }
    )


@pytest.fixture
def sample_backtest_result() -> BacktestResult:
    """Minimal BacktestResult for testing."""
    return BacktestResult(
        daily_returns=pd.Series([0.001, -0.002, 0.003], dtype=float),
        oos_sharpe=1.25,
        oos_cagr=0.12,
        max_drawdown=-0.08,
        annual_turnover=4.5,
        cost_drag_pct=0.3,
        per_fold_sharpe=[1.1, 1.3, 1.35],
        per_factor_contribution={"momentum": 0.6, "value": 0.4},
    )


class TestResearchStoreInit:
    """Tests for table creation on init."""

    def test_tables_created_on_init(self, store: ResearchStore) -> None:
        """All four tables must exist after initialization."""
        tables = store._conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "ohlcv" in table_names
        assert "fundamentals" in table_names
        assert "features" in table_names
        assert "backtest_results" in table_names
        assert "gate_verdicts" in table_names

    def test_context_manager(self, tmp_path: Path) -> None:
        """ResearchStore works as a context manager."""
        db_path = tmp_path / "ctx.duckdb"
        with ResearchStore(db_path) as s:
            tables = s._conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
            assert len(tables) >= 4


class TestOHLCV:
    """Tests for store_ohlcv and load_ohlcv."""

    def test_write_read_round_trip(self, store: ResearchStore, sample_ohlcv: pd.DataFrame) -> None:
        """Write OHLCV data and read it back — content must match."""
        diag_w = store.store_ohlcv(sample_ohlcv)
        assert not diag_w.has_errors

        result, diag_r = store.load_ohlcv(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 12, 31))
        assert not diag_r.has_errors
        assert len(result) == 4
        assert set(result[COL_SYMBOL].unique()) == {"AAPL", "MSFT"}

    def test_symbol_filtering(self, store: ResearchStore, sample_ohlcv: pd.DataFrame) -> None:
        """Only requested symbols are returned."""
        store.store_ohlcv(sample_ohlcv)
        result, diag = store.load_ohlcv(["AAPL"], date(2024, 1, 1), date(2024, 12, 31))

        assert len(result) == 2
        assert all(result[COL_SYMBOL] == "AAPL")

    def test_date_range_filtering(self, store: ResearchStore, sample_ohlcv: pd.DataFrame) -> None:
        """Only rows within the date range are returned."""
        store.store_ohlcv(sample_ohlcv)
        result, diag = store.load_ohlcv(["AAPL", "MSFT"], date(2024, 1, 3), date(2024, 1, 3))

        assert len(result) == 2
        dates = result[COL_DATE].unique()
        assert len(dates) == 1

    def test_upsert_overwrites_existing(self, store: ResearchStore, sample_ohlcv: pd.DataFrame) -> None:
        """Writing the same (date, symbol) again should overwrite, not duplicate."""
        store.store_ohlcv(sample_ohlcv)

        updated = pd.DataFrame(
            {
                COL_DATE: [date(2024, 1, 2)],
                COL_SYMBOL: ["AAPL"],
                COL_OPEN: [999.0],
                COL_HIGH: [999.0],
                COL_LOW: [999.0],
                COL_CLOSE: [999.0],
                COL_VOLUME: [999],
            }
        )
        store.store_ohlcv(updated)

        result, _ = store.load_ohlcv(["AAPL"], date(2024, 1, 2), date(2024, 1, 2))
        assert len(result) == 1
        assert result.iloc[0][COL_CLOSE] == 999.0

    def test_empty_database_returns_empty_df(self, store: ResearchStore) -> None:
        """Reading from empty database returns empty DataFrame with correct columns."""
        result, diag = store.load_ohlcv(["AAPL"], date(2024, 1, 1), date(2024, 12, 31))
        assert len(result) == 0
        expected_cols = {COL_DATE, COL_SYMBOL, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME}
        assert expected_cols == set(result.columns)

    def test_empty_symbols_returns_empty_df(self, store: ResearchStore) -> None:
        """Passing empty symbol list returns empty DataFrame."""
        result, diag = store.load_ohlcv([], date(2024, 1, 1), date(2024, 12, 31))
        assert len(result) == 0


class TestFundamentals:
    """Tests for store_fundamentals and load_fundamentals."""

    def test_write_read_round_trip(
        self,
        store: ResearchStore,
        sample_fundamentals: pd.DataFrame,
    ) -> None:
        """Write long-format XBRL facts and read them back."""
        diag_w = store.store_fundamentals(sample_fundamentals)
        assert not diag_w.has_errors

        result, diag_r = store.load_fundamentals(
            ["AAPL", "MSFT"],
            date(2023, 1, 1),
            date(2023, 12, 31),
        )
        assert not diag_r.has_errors
        # 6 input rows but 1 has NaN value (kept — NaN value is allowed, only PK NaN drops)
        assert len(result) == 6
        assert set(result[COL_SYMBOL].unique()) == {"AAPL", "MSFT"}
        assert set(result["metric_name"].unique()) == {"revenue", "net_income"}

    def test_nan_value_preserved(
        self,
        store: ResearchStore,
        sample_fundamentals: pd.DataFrame,
    ) -> None:
        """NaN in `value` is kept (XBRL parse failures) — only PK NaN drops rows."""
        store.store_fundamentals(sample_fundamentals)
        result, _ = store.load_fundamentals(
            ["MSFT"],
            date(2023, 7, 27),
            date(2023, 7, 27),
            metric_names=["net_income"],
        )
        assert len(result) == 1
        assert pd.isna(result.iloc[0]["value"])

    def test_pk_nan_rows_dropped(self, store: ResearchStore) -> None:
        """Rows with NULL in PK columns (date/symbol/metric_name/period_end) are dropped."""
        bad = pd.DataFrame(
            {
                COL_DATE: [date(2023, 5, 1), None, date(2023, 5, 1)],
                COL_SYMBOL: ["AAPL", "AAPL", None],
                "metric_name": ["revenue", "revenue", "revenue"],
                "value": [100.0, 200.0, 300.0],
                "filing_type": ["10-Q", "10-Q", "10-Q"],
                "period_end": [date(2023, 4, 1), date(2023, 4, 1), date(2023, 4, 1)],
            }
        )
        diag = store.store_fundamentals(bad)
        assert not diag.has_errors
        assert diag.has_warnings  # dropped PK-NaN rows warning

        result, _ = store.load_fundamentals(
            ["AAPL"],
            date(2023, 1, 1),
            date(2023, 12, 31),
        )
        assert len(result) == 1  # only the valid row survived
        assert result.iloc[0]["value"] == 100.0

    def test_symbol_filtering(
        self,
        store: ResearchStore,
        sample_fundamentals: pd.DataFrame,
    ) -> None:
        """Only requested symbols are returned."""
        store.store_fundamentals(sample_fundamentals)
        result, _ = store.load_fundamentals(
            ["AAPL"],
            date(2023, 1, 1),
            date(2023, 12, 31),
        )
        assert all(result[COL_SYMBOL] == "AAPL")
        assert len(result) == 4  # 2 filings × 2 metrics

    def test_date_range_filtering_on_filing_date(
        self,
        store: ResearchStore,
        sample_fundamentals: pd.DataFrame,
    ) -> None:
        """Filter uses filing_date (PiT key), NOT period_end."""
        store.store_fundamentals(sample_fundamentals)
        # AAPL 10-Q filed 2023-05-01 covers period ending 2023-04-01.
        # Query by filing date 2023-05-01 must return it; the period_end is
        # outside the window but that's intentional (PiT key is filing date).
        result, _ = store.load_fundamentals(
            ["AAPL"],
            date(2023, 5, 1),
            date(2023, 5, 1),
        )
        assert len(result) == 2  # revenue + net_income for the 10-Q
        assert all(pd.to_datetime(result[COL_DATE]).dt.date == date(2023, 5, 1))

    def test_metric_names_filter(
        self,
        store: ResearchStore,
        sample_fundamentals: pd.DataFrame,
    ) -> None:
        """metric_names=[...] filters to the subset; None returns all."""
        store.store_fundamentals(sample_fundamentals)

        result, _ = store.load_fundamentals(
            ["AAPL", "MSFT"],
            date(2023, 1, 1),
            date(2023, 12, 31),
            metric_names=["revenue"],
        )
        assert len(result) == 3  # 2 AAPL + 1 MSFT revenue rows
        assert set(result["metric_name"].unique()) == {"revenue"}

    def test_upsert_overwrites_existing(
        self,
        store: ResearchStore,
        sample_fundamentals: pd.DataFrame,
    ) -> None:
        """Re-writing the same PK (date, symbol, metric_name, period_end) overwrites."""
        store.store_fundamentals(sample_fundamentals)

        updated = pd.DataFrame(
            {
                COL_DATE: [date(2023, 5, 1)],
                COL_SYMBOL: ["AAPL"],
                "metric_name": ["revenue"],
                "value": [999999.0],
                "filing_type": ["10-Q"],
                "period_end": [date(2023, 4, 1)],
            }
        )
        store.store_fundamentals(updated)

        result, _ = store.load_fundamentals(
            ["AAPL"],
            date(2023, 5, 1),
            date(2023, 5, 1),
            metric_names=["revenue"],
        )
        assert len(result) == 1
        assert result.iloc[0]["value"] == 999999.0

    def test_empty_database_returns_empty_df(self, store: ResearchStore) -> None:
        """Reading from an empty fundamentals table returns an empty DataFrame with correct columns."""
        result, _ = store.load_fundamentals(
            ["AAPL"],
            date(2023, 1, 1),
            date(2023, 12, 31),
        )
        assert len(result) == 0
        expected = {COL_DATE, COL_SYMBOL, "metric_name", "value", "filing_type", "period_end"}
        assert expected == set(result.columns)

    def test_empty_symbols_returns_empty_df(self, store: ResearchStore) -> None:
        """Passing empty symbol list returns empty DataFrame with a warning."""
        result, diag = store.load_fundamentals(
            [],
            date(2023, 1, 1),
            date(2023, 12, 31),
        )
        assert len(result) == 0
        assert diag.has_warnings

    def test_missing_required_columns_errors(self, store: ResearchStore) -> None:
        """Missing any required column surfaces a diagnostic error."""
        bad = pd.DataFrame(
            {
                COL_DATE: [date(2023, 5, 1)],
                COL_SYMBOL: ["AAPL"],
                "metric_name": ["revenue"],
                # missing: value, filing_type, period_end
            }
        )
        diag = store.store_fundamentals(bad)
        assert diag.has_errors


class TestFeatures:
    """Tests for store_features and load_features."""

    def test_write_read_round_trip(self, store: ResearchStore, sample_features: pd.DataFrame) -> None:
        """Write features and read them back."""
        diag_w = store.store_features(sample_features, date(2024, 1, 2))
        assert not diag_w.has_errors

        result, diag_r = store.load_features(date(2024, 1, 2))
        assert not diag_r.has_errors
        assert len(result) == 4
        assert set(result["factor_name"].unique()) == {"momentum", "value"}

    def test_empty_features_returns_empty(self, store: ResearchStore) -> None:
        """Reading features for a date with no data returns empty DataFrame."""
        result, diag = store.load_features(date(2024, 6, 15))
        assert len(result) == 0


class TestBacktestResults:
    """Tests for store_backtest_result and load_backtest_result."""

    def test_store_and_load_round_trip(
        self,
        store: ResearchStore,
        sample_backtest_result: BacktestResult,
    ) -> None:
        """Store a backtest result and load it back — metrics must match."""
        run_id = "test-run-001"
        diag_w = store.store_backtest_result(sample_backtest_result, run_id)
        assert not diag_w.has_errors

        loaded, diag_r = store.load_backtest_result(run_id)
        assert not diag_r.has_errors
        assert loaded is not None
        assert loaded.oos_sharpe == pytest.approx(1.25)
        assert loaded.oos_cagr == pytest.approx(0.12)
        assert loaded.max_drawdown == pytest.approx(-0.08)
        assert loaded.annual_turnover == pytest.approx(4.5)
        assert loaded.cost_drag_pct == pytest.approx(0.3)
        assert loaded.per_fold_sharpe == [1.1, 1.3, 1.35]
        assert loaded.per_factor_contribution == {"momentum": 0.6, "value": 0.4}

    def test_load_nonexistent_returns_none(self, store: ResearchStore) -> None:
        """Loading a nonexistent run_id returns None with a warning."""
        loaded, diag = store.load_backtest_result("no-such-id")
        assert loaded is None
        assert diag.has_warnings

    def test_upsert_overwrites(
        self,
        store: ResearchStore,
        sample_backtest_result: BacktestResult,
    ) -> None:
        """Storing with the same run_id overwrites the previous result."""
        run_id = "overwrite-test"
        store.store_backtest_result(sample_backtest_result, run_id)

        # Create a different result with a different sharpe
        updated = BacktestResult(
            daily_returns=pd.Series([0.01], dtype=float),
            oos_sharpe=2.0,
            oos_cagr=0.20,
            max_drawdown=-0.05,
            annual_turnover=3.0,
            cost_drag_pct=0.1,
            per_fold_sharpe=[2.0],
            per_factor_contribution={"momentum": 1.0},
        )
        store.store_backtest_result(updated, run_id)

        loaded, _ = store.load_backtest_result(run_id)
        assert loaded is not None
        assert loaded.oos_sharpe == pytest.approx(2.0)

    def test_daily_returns_preserved(
        self,
        store: ResearchStore,
        sample_backtest_result: BacktestResult,
    ) -> None:
        """daily_returns Series values survive the round-trip."""
        run_id = "daily-ret-test"
        store.store_backtest_result(sample_backtest_result, run_id)

        loaded, _ = store.load_backtest_result(run_id)
        assert loaded is not None
        assert list(loaded.daily_returns.values) == pytest.approx([0.001, -0.002, 0.003])


class TestGateVerdicts:
    """Tests for write_gate_verdict and read_gate_verdicts."""

    def test_write_and_read(self, store: ResearchStore) -> None:
        """Write gate verdicts and read them back."""
        gate_results = {
            "G0": {"passed": True, "metric_value": 0.95},
            "G1": {"passed": False, "metric_value": 0.01},
        }
        diag = store.write_gate_verdict("momentum", gate_results)
        assert not diag.has_errors

        result = store.read_gate_verdicts("momentum")
        assert len(result) == 2
        assert set(result["gate_name"].tolist()) == {"G0", "G1"}

    def test_read_all_verdicts(self, store: ResearchStore) -> None:
        """Read verdicts without factor filter returns all."""
        store.write_gate_verdict("momentum", {"G0": {"passed": True, "metric_value": 0.9}})
        store.write_gate_verdict("value", {"G0": {"passed": False, "metric_value": 0.3}})

        result = store.read_gate_verdicts()
        assert len(result) == 2
        assert set(result["factor_name"].tolist()) == {"momentum", "value"}
