"""Property-based test: PiT enforcement NEVER allows future data.

Uses Hypothesis to generate arbitrary dates, publication lags, and max-age values,
then verifies two invariants:
  1. No non-NaN value has an effective available date after as_of_date.
  2. No non-NaN value is older than max_age_days.

These invariants must hold for ALL possible inputs -- not just hand-picked dates.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from nyse_core.pit import enforce_pit_lags

_DATE_STRATEGY = st.dates(min_value=date(2018, 1, 1), max_value=date(2025, 12, 31))


# ── Invariant 1: No future data survives ────────────────────────────────────


@given(
    as_of_date=_DATE_STRATEGY,
    pub_lag=st.integers(min_value=0, max_value=90),
    max_age=st.integers(min_value=1, max_value=365),
    n_rows=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=200, deadline=None)
def test_no_future_data_in_output(
    as_of_date: date,
    pub_lag: int,
    max_age: int,
    n_rows: int,
) -> None:
    """After PiT enforcement, every non-NaN value must have
    filing_date + publication_lag <= as_of_date."""
    rng = np.random.default_rng(42)
    offsets = rng.integers(-max_age * 2, max_age, size=n_rows)
    dates = [as_of_date + timedelta(days=int(d)) for d in offsets]

    data = pd.DataFrame(
        {
            "date": dates,
            "feature_a": rng.standard_normal(n_rows),
            "feature_b": rng.standard_normal(n_rows),
        }
    )

    result, _ = enforce_pit_lags(
        data=data,
        publication_lags={"feature_a": pub_lag, "feature_b": 0},
        as_of_date=as_of_date,
        max_age_days=max_age,
    )

    as_of_ts = pd.Timestamp(as_of_date)
    feature_dates = pd.to_datetime(result["date"])

    for col in ["feature_a", "feature_b"]:
        lag = {"feature_a": pub_lag, "feature_b": 0}[col]
        non_nan = result[col].notna()
        if non_nan.any():
            available = feature_dates[non_nan] + pd.Timedelta(days=lag)
            assert (available <= as_of_ts).all(), (
                f"Future data leaked in '{col}': available_dates > {as_of_date}"
            )


# ── Invariant 2: No stale data survives ─────────────────────────────────────


@given(
    as_of_date=_DATE_STRATEGY,
    pub_lag=st.integers(min_value=0, max_value=90),
    max_age=st.integers(min_value=1, max_value=365),
    n_rows=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=200, deadline=None)
def test_no_stale_data_in_output(
    as_of_date: date,
    pub_lag: int,
    max_age: int,
    n_rows: int,
) -> None:
    """After PiT enforcement, no non-NaN value is older than max_age_days."""
    rng = np.random.default_rng(42)
    offsets = rng.integers(-max_age * 2, max_age, size=n_rows)
    dates = [as_of_date + timedelta(days=int(d)) for d in offsets]

    data = pd.DataFrame(
        {
            "date": dates,
            "feature_a": rng.standard_normal(n_rows),
        }
    )

    result, _ = enforce_pit_lags(
        data=data,
        publication_lags={"feature_a": pub_lag},
        as_of_date=as_of_date,
        max_age_days=max_age,
    )

    as_of_ts = pd.Timestamp(as_of_date)
    feature_dates = pd.to_datetime(result["date"])
    non_nan = result["feature_a"].notna()
    if non_nan.any():
        ages = (as_of_ts - feature_dates[non_nan]).dt.days
        assert (ages <= max_age).all(), f"Stale data survived: max_age={max_age}, found age {ages.max()}"


# ── Edge case: empty DataFrame ──────────────────────────────────────────────


@given(
    as_of_date=_DATE_STRATEGY,
    max_age=st.integers(min_value=30, max_value=365),
)
@settings(max_examples=100, deadline=None)
def test_empty_dataframe_no_crash(as_of_date: date, max_age: int) -> None:
    """PiT enforcement on empty DataFrame must not crash."""
    data = pd.DataFrame(
        {
            "date": pd.Series(dtype="datetime64[ns]"),
            "feature_a": pd.Series(dtype="float64"),
        }
    )
    result, diag = enforce_pit_lags(
        data=data,
        publication_lags={"feature_a": 5},
        as_of_date=as_of_date,
        max_age_days=max_age,
    )
    assert len(result) == 0


# ── Deterministic boundary tests ────────────────────────────────────────────


def test_all_future_returns_all_nan() -> None:
    """If every row is filed in the future, all features must be NaN."""
    as_of = date(2020, 6, 15)
    data = pd.DataFrame(
        {
            "date": [as_of + timedelta(days=d) for d in [1, 5, 10]],
            "feature_a": [1.0, 2.0, 3.0],
        }
    )
    result, _ = enforce_pit_lags(
        data=data,
        publication_lags={"feature_a": 0},
        as_of_date=as_of,
        max_age_days=365,
    )
    assert result["feature_a"].isna().all()


def test_boundary_exact_date_survives() -> None:
    """A feature filed exactly on as_of_date with 0 lag must survive."""
    as_of = date(2020, 6, 15)
    data = pd.DataFrame({"date": [as_of], "feature_a": [42.0]})
    result, _ = enforce_pit_lags(
        data=data,
        publication_lags={"feature_a": 0},
        as_of_date=as_of,
        max_age_days=365,
    )
    assert result["feature_a"].iloc[0] == 42.0


def test_boundary_max_age_exact_survives() -> None:
    """A feature exactly at max_age boundary survives (age == max_age is NOT stale)."""
    as_of = date(2020, 6, 15)
    data = pd.DataFrame(
        {
            "date": [as_of - timedelta(days=30)],
            "feature_a": [42.0],
        }
    )
    result, _ = enforce_pit_lags(
        data=data,
        publication_lags={"feature_a": 0},
        as_of_date=as_of,
        max_age_days=30,
    )
    assert result["feature_a"].iloc[0] == 42.0


def test_boundary_max_age_plus_one_is_nan() -> None:
    """A feature at max_age+1 must be NaN'd."""
    as_of = date(2020, 6, 15)
    data = pd.DataFrame(
        {
            "date": [as_of - timedelta(days=31)],
            "feature_a": [42.0],
        }
    )
    result, _ = enforce_pit_lags(
        data=data,
        publication_lags={"feature_a": 0},
        as_of_date=as_of,
        max_age_days=30,
    )
    assert pd.isna(result["feature_a"].iloc[0])


def test_publication_lag_blocks_recent_filing() -> None:
    """A feature filed 5 days ago with 10-day pub lag must be NaN."""
    as_of = date(2020, 6, 15)
    data = pd.DataFrame(
        {
            "date": [as_of - timedelta(days=5)],
            "feature_a": [99.0],
        }
    )
    result, _ = enforce_pit_lags(
        data=data,
        publication_lags={"feature_a": 10},
        as_of_date=as_of,
        max_age_days=365,
    )
    # Filed 5 days ago + 10 day lag = available in 5 days => future => NaN
    assert pd.isna(result["feature_a"].iloc[0])


def test_publication_lag_allows_old_filing() -> None:
    """A feature filed 15 days ago with 10-day pub lag must survive."""
    as_of = date(2020, 6, 15)
    data = pd.DataFrame(
        {
            "date": [as_of - timedelta(days=15)],
            "feature_a": [99.0],
        }
    )
    result, _ = enforce_pit_lags(
        data=data,
        publication_lags={"feature_a": 10},
        as_of_date=as_of,
        max_age_days=365,
    )
    assert result["feature_a"].iloc[0] == 99.0


def test_diagnostics_reports_nan_counts() -> None:
    """Diagnostics should report how many values were NaN'd."""
    as_of = date(2020, 6, 15)
    data = pd.DataFrame(
        {
            "date": [
                as_of + timedelta(days=1),  # future
                as_of - timedelta(days=5),  # ok
                as_of - timedelta(days=500),  # stale
            ],
            "feature_a": [1.0, 2.0, 3.0],
        }
    )
    _, diag = enforce_pit_lags(
        data=data,
        publication_lags={"feature_a": 0},
        as_of_date=as_of,
        max_age_days=30,
    )
    messages = [m.message for m in diag.messages]
    assert any("future-dated" in m for m in messages)
    assert any("stale" in m for m in messages)
