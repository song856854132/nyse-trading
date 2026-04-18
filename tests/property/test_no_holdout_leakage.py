"""Property test: iron rule 1 is enforced across every nyse_core entrypoint.

For every function in ``nyse_core`` that accepts a date range, feeding any date
strictly greater than ``HOLDOUT_BOUNDARY`` (2023-12-31) must raise
``HoldoutLeakageError`` before any data is processed.

Also scans ``research.duckdb`` at test time and asserts that the maximum date
in the ``ohlcv`` table (if present) is 2023-12-31 or earlier. A database
containing holdout-era bars is itself a violation — the guarded functions
would refuse to process it, but the cheaper check is "holdout data was never
ingested in the first place".
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from nyse_core.attribution import compute_attribution
from nyse_core.backtest import run_walk_forward_backtest
from nyse_core.contracts import HOLDOUT_BOUNDARY, HoldoutLeakageError
from nyse_core.cv import PurgedWalkForwardCV
from nyse_core.pit import enforce_pit_lags
from nyse_core.research_pipeline import ResearchPipeline
from nyse_core.universe import get_universe_at_date

# Strategy: every date generated is STRICTLY greater than HOLDOUT_BOUNDARY.
# 2025-12-31 is the outer edge of the documented holdout window; we do not
# need to probe beyond it to prove the boundary.
_HOLDOUT_DATE = st.dates(
    min_value=HOLDOUT_BOUNDARY + timedelta(days=1),
    max_value=date(2025, 12, 31),
)

# Small synthetic OHLCV frame placed entirely inside the holdout window so the
# DataFrame-level guards fire.
_ROW_COUNT = st.integers(min_value=1, max_value=4)


def _make_ohlcv(sample_date: date, n_rows: int) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "date": [sample_date] * n_rows,
            "symbol": [f"SYM{i}" for i in range(n_rows)],
            "close": rng.uniform(10, 200, size=n_rows),
            "volume": rng.integers(1_000_000, 10_000_000, size=n_rows),
        }
    )


# ── pit.enforce_pit_lags guards as_of_date ───────────────────────────────────


@given(as_of=_HOLDOUT_DATE)
@settings(max_examples=50, deadline=None)
def test_pit_rejects_holdout_as_of_date(as_of: date) -> None:
    data = pd.DataFrame({"date": [as_of - timedelta(days=30)], "feature_a": [1.0]})
    with pytest.raises(HoldoutLeakageError, match="pit.enforce_pit_lags"):
        enforce_pit_lags(
            data=data,
            publication_lags={"feature_a": 0},
            as_of_date=as_of,
            max_age_days=365,
        )


# ── attribution.compute_attribution guards period_start / period_end ─────────


@given(period_start=_HOLDOUT_DATE)
@settings(max_examples=50, deadline=None)
def test_attribution_rejects_holdout_period_start(period_start: date) -> None:
    with pytest.raises(HoldoutLeakageError, match="attribution"):
        compute_attribution(
            portfolio_weights=pd.DataFrame(columns=["date", "symbol", "weight"]),
            stock_returns=pd.DataFrame(columns=["date", "symbol", "return"]),
            factor_exposures=pd.DataFrame(columns=["date", "symbol", "factor_name", "exposure"]),
            sector_map=pd.Series(dtype=str),
            period_start=period_start,
        )


@given(period_end=_HOLDOUT_DATE)
@settings(max_examples=50, deadline=None)
def test_attribution_rejects_holdout_period_end(period_end: date) -> None:
    with pytest.raises(HoldoutLeakageError, match="attribution"):
        compute_attribution(
            portfolio_weights=pd.DataFrame(columns=["date", "symbol", "weight"]),
            stock_returns=pd.DataFrame(columns=["date", "symbol", "return"]),
            factor_exposures=pd.DataFrame(columns=["date", "symbol", "factor_name", "exposure"]),
            sector_map=pd.Series(dtype=str),
            period_end=period_end,
        )


# ── universe.get_universe_at_date guards target_date ─────────────────────────


@given(target=_HOLDOUT_DATE)
@settings(max_examples=50, deadline=None)
def test_universe_rejects_holdout_target_date(target: date) -> None:
    changes = pd.DataFrame(columns=["date", "symbol", "action"])
    with pytest.raises(HoldoutLeakageError, match="universe"):
        get_universe_at_date(
            constituency_changes=changes,
            target_date=target,
            initial_members=["AAPL", "MSFT"],
        )


# ── cv.PurgedWalkForwardCV.split guards its DatetimeIndex ────────────────────


@given(bad_date=_HOLDOUT_DATE)
@settings(max_examples=50, deadline=None)
def test_cv_split_rejects_holdout_datetime_index(bad_date: date) -> None:
    # Mostly research-era dates with one holdout-era date at the end.
    research_dates = pd.date_range("2020-01-01", "2023-12-31", freq="B")
    dates = pd.DatetimeIndex(list(research_dates) + [pd.Timestamp(bad_date)])
    cv = PurgedWalkForwardCV(
        n_folds=2,
        min_train_days=252,
        test_days=21,
        purge_days=5,
        embargo_days=5,
    )
    with pytest.raises(HoldoutLeakageError, match="cv.PurgedWalkForwardCV.split"):
        # split is a generator — consume it to trigger the guard.
        list(cv.split(dates))


# ── backtest.run_walk_forward_backtest guards feature_matrix.index ───────────


@given(bad_date=_HOLDOUT_DATE)
@settings(max_examples=30, deadline=None)
def test_backtest_rejects_holdout_feature_matrix_index(bad_date: date) -> None:
    idx = pd.DatetimeIndex([pd.Timestamp("2023-12-01"), pd.Timestamp(bad_date)])
    feature_matrix = pd.DataFrame({"f1": [0.1, 0.2]}, index=idx)
    returns = pd.Series([0.01, 0.02], index=idx)

    cv = PurgedWalkForwardCV(
        n_folds=1,
        min_train_days=1,
        test_days=1,
        purge_days=0,
        embargo_days=0,
    )

    def _factory() -> object:
        raise AssertionError("factory should never be reached")

    def _alloc(_arr: np.ndarray) -> np.ndarray:
        return np.array([0.0])

    def _risk(arr: np.ndarray) -> np.ndarray:
        return arr

    def _cost(_prev: np.ndarray, _new: np.ndarray) -> float:
        return 0.0

    with pytest.raises(HoldoutLeakageError, match="backtest.run_walk_forward_backtest"):
        run_walk_forward_backtest(
            feature_matrix=feature_matrix,
            returns=returns,
            cv=cv,
            model_factory=_factory,
            allocator_fn=_alloc,
            risk_fn=_risk,
            cost_fn=_cost,
        )


# ── research_pipeline.compute_feature_matrix guards rebalance_date + ohlcv ───


@given(rebalance=_HOLDOUT_DATE, n_rows=_ROW_COUNT)
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_research_pipeline_rejects_holdout_rebalance_date(rebalance: date, n_rows: int) -> None:
    from nyse_core.features.registry import FactorRegistry

    pipeline = ResearchPipeline(registry=FactorRegistry())
    ohlcv = _make_ohlcv(date(2023, 12, 1), n_rows)  # research-era data
    with pytest.raises(HoldoutLeakageError, match="compute_feature_matrix"):
        pipeline.compute_feature_matrix(ohlcv=ohlcv, rebalance_date=rebalance)


@given(bad_date=_HOLDOUT_DATE, n_rows=_ROW_COUNT)
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_research_pipeline_rejects_holdout_ohlcv_date(bad_date: date, n_rows: int) -> None:
    from nyse_core.features.registry import FactorRegistry

    pipeline = ResearchPipeline(registry=FactorRegistry())
    ohlcv = _make_ohlcv(bad_date, n_rows)
    with pytest.raises(HoldoutLeakageError, match="compute_feature_matrix"):
        pipeline.compute_feature_matrix(ohlcv=ohlcv, rebalance_date=date(2023, 6, 30))


@given(bad_date=_HOLDOUT_DATE, n_rows=_ROW_COUNT)
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_walk_forward_validation_rejects_holdout_ohlcv(bad_date: date, n_rows: int) -> None:
    from nyse_core.features.registry import FactorRegistry

    pipeline = ResearchPipeline(registry=FactorRegistry())
    ohlcv = _make_ohlcv(bad_date, n_rows)
    with pytest.raises(HoldoutLeakageError, match="run_walk_forward_validation"):
        pipeline.run_walk_forward_validation(ohlcv=ohlcv)


# ── Boundary sanity: the day equal to the boundary passes ────────────────────


def test_boundary_date_is_accepted() -> None:
    """Iron rule is 'strictly greater than'. The boundary itself is research."""
    data = pd.DataFrame({"date": [HOLDOUT_BOUNDARY], "feature_a": [1.0]})
    _result, _diag = enforce_pit_lags(
        data=data,
        publication_lags={"feature_a": 0},
        as_of_date=HOLDOUT_BOUNDARY,
        max_age_days=365,
    )


# ── research.duckdb sanity check (iron rule 1, enforcement via data too) ─────


def test_research_duckdb_has_no_holdout_dates() -> None:
    """If research.duckdb exists, its ohlcv MAX(date) must be <= 2023-12-31.

    Skips gracefully if the database has not been built yet — early-stage
    iterations may run before data ingestion.
    """
    db_path = Path(__file__).resolve().parents[2] / "research.duckdb"
    if not db_path.exists():
        pytest.skip(f"research.duckdb not present at {db_path}")

    try:
        import duckdb
    except ImportError:
        pytest.skip("duckdb not installed")

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
        }
        if "ohlcv" not in tables:
            pytest.skip("ohlcv table not present in research.duckdb")

        row = conn.execute("SELECT MAX(date) FROM ohlcv").fetchone()
    finally:
        conn.close()

    if row is None or row[0] is None:
        pytest.skip("ohlcv table is empty")

    max_date = row[0]
    if isinstance(max_date, pd.Timestamp):
        max_date = max_date.date()
    assert max_date <= HOLDOUT_BOUNDARY, (
        f"research.duckdb ohlcv contains holdout-era data: MAX(date)={max_date} "
        f"(boundary={HOLDOUT_BOUNDARY}). Iron rule 1 violated."
    )
