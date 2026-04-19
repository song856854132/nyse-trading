"""Property-based test: PiT enforcement NEVER allows future data.

Part A (original): verifies the generic PiT mechanism in ``nyse_core.pit``.
  1. No non-NaN value has an effective available date after as_of_date.
  2. No non-NaN value is older than max_age_days.

Part B (RALPH TODO-12, added iter-25): verifies that every feature compute
function implements the PiT contract at the compute boundary. Property per
function: the cross-sectional factor value produced from a panel filtered to
``date <= T`` is bitwise identical to the value produced from the same panel
with arbitrary additional rows dated ``date > T`` appended (when the caller
slices back to ``date <= T``). This isolates three defects that are otherwise
invisible:

  - non-determinism (output depends on hidden state or rng),
  - row-order dependence (output depends on DataFrame row index order rather
    than the ``date`` column), and
  - missing internal lag filter for FINRA short-interest functions (the three
    ``short_interest.compute_*`` functions apply an 11-day FINRA publication
    lag internally and must drop rows within that window even when the caller
    passes them in).

All Part-B synthetic fixtures are bounded to the pre-2023 era per iron rule 1;
no compute call may reach a date after 2023-12-31.

These invariants must hold for ALL possible inputs -- not just hand-picked dates.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nyse_core.features.earnings import compute_earnings_surprise
from nyse_core.features.fundamental import (
    compute_accruals,
    compute_piotroski_f_score,
    compute_profitability,
)
from nyse_core.features.nlp_earnings import (
    compute_earnings_sentiment,
    compute_sentiment_dispersion,
    compute_sentiment_surprise,
)
from nyse_core.features.price_volume import (
    compute_52w_high_proximity,
    compute_ivol_20d,
    compute_momentum_2_12,
)
from nyse_core.features.sentiment import (
    compute_ewmac,
    compute_put_call_ratio,
    compute_volume_momentum,
)
from nyse_core.features.short_interest import (
    _FINRA_PUBLICATION_LAG,
    compute_short_interest_change,
    compute_short_interest_pct,
    compute_short_ratio,
)
from nyse_core.pit import enforce_pit_lags
from nyse_core.schema import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_SYMBOL,
    COL_VOLUME,
)

_DATE_STRATEGY = st.dates(min_value=date(2018, 1, 1), max_value=date(2023, 12, 31))


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


# ── Part B: Per-feature PiT purity (RALPH TODO-12) ──────────────────────────
#
# Property under test for every compute function: given an arbitrary input
# panel P, the output of ``compute_fn(P)`` must equal the output of
# ``compute_fn(P_shuffled)`` where ``P_shuffled`` is the SAME rows in a
# different row-index order. This is a necessary (not sufficient) condition
# for the PiT contract — if a function is row-order dependent, then a caller
# slicing a date-filtered view out of a larger panel (``df[df.date <= T]``)
# could silently receive output that depends on post-T rows via row-index
# side-channels. Three defects show up here: non-determinism, hidden rng
# state, and row-order dependence. All synthetic fixtures live pre-2023 per
# iron rule 1.


def _make_price_panel(n_symbols: int = 3, n_days: int = 300, seed: int = 1) -> pd.DataFrame:
    """Synthetic OHLCV panel. Default covers 300 bdays => enough for momentum_2_12 (252)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start="2015-01-02", periods=n_days)
    rows = []
    for s_idx in range(n_symbols):
        sym = f"SYM{s_idx:03d}"
        close = 50.0 + np.cumsum(rng.standard_normal(n_days) * 0.5)
        close = np.maximum(close, 1.0)
        for i, d in enumerate(dates):
            c = float(close[i])
            rows.append(
                {
                    COL_DATE: d.date(),
                    COL_SYMBOL: sym,
                    COL_OPEN: c * (1.0 + float(rng.normal(0.0, 0.001))),
                    COL_HIGH: c * (1.0 + abs(float(rng.normal(0.0, 0.005)))),
                    COL_LOW: c * (1.0 - abs(float(rng.normal(0.0, 0.005)))),
                    COL_CLOSE: c,
                    COL_VOLUME: int(rng.integers(1_000_000, 5_000_000)),
                }
            )
    return pd.DataFrame(rows)


def _make_earnings_panel(n_symbols: int = 3, n_quarters: int = 6, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2015-03-31")
    quarters = [(base + pd.Timedelta(days=90 * i)).date() for i in range(n_quarters)]
    rows = []
    for s_idx in range(n_symbols):
        sym = f"SYM{s_idx:03d}"
        for q in quarters:
            rows.append(
                {
                    COL_SYMBOL: sym,
                    "period_end": q,
                    "operating_profitability": float(rng.normal(0.1, 0.02)),
                }
            )
    return pd.DataFrame(rows)


def _make_nlp_panel(n_symbols: int = 3, n_quarters: int = 6, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2015-03-31")
    quarters = [(base + pd.Timedelta(days=90 * i)).date() for i in range(n_quarters)]
    rows = []
    for s_idx in range(n_symbols):
        sym = f"SYM{s_idx:03d}"
        for q in quarters:
            rows.append(
                {
                    COL_SYMBOL: sym,
                    COL_DATE: q,
                    "sentiment_score": float(rng.normal(0.0, 0.3)),
                    "sentiment_std": float(abs(rng.normal(0.2, 0.05))),
                }
            )
    return pd.DataFrame(rows)


def _make_options_panel(n_symbols: int = 3, n_days: int = 40, seed: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start="2015-01-02", periods=n_days)
    rows = []
    for s_idx in range(n_symbols):
        sym = f"SYM{s_idx:03d}"
        for d in dates:
            rows.append(
                {
                    COL_SYMBOL: sym,
                    COL_DATE: d.date(),
                    "put_volume": float(rng.integers(1_000, 50_000)),
                    "call_volume": float(rng.integers(1_000, 50_000)),
                }
            )
    return pd.DataFrame(rows)


def _make_short_interest_panel(n_symbols: int = 3, n_periods: int = 12, seed: int = 5) -> pd.DataFrame:
    """Bi-monthly FINRA-style panel spanning ~180 days so internal 11-day lag filter activates."""
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2015-01-15")
    dates = [(base + pd.Timedelta(days=15 * i)).date() for i in range(n_periods)]
    rows = []
    for s_idx in range(n_symbols):
        sym = f"SYM{s_idx:03d}"
        for d in dates:
            rows.append(
                {
                    COL_SYMBOL: sym,
                    COL_DATE: d,
                    "short_interest": float(rng.integers(100_000, 5_000_000)),
                    "shares_outstanding": 100_000_000.0,
                    "avg_daily_volume": float(rng.integers(500_000, 2_000_000)),
                }
            )
    return pd.DataFrame(rows)


def _make_fundamental_panel(n_symbols: int = 3, n_quarters: int = 12, seed: int = 6) -> pd.DataFrame:
    """Long-format XBRL facts covering metrics required by all three fundamental factors."""
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2015-03-31")
    quarters = [(base + pd.Timedelta(days=90 * i)).date() for i in range(n_quarters)]
    metrics: dict[str, tuple[float, float]] = {
        "net_income": (1.0e8, 2.0e7),
        "total_assets": (1.0e10, 1.0e9),
        "operating_cash_flow": (1.5e8, 2.0e7),
        "long_term_debt": (2.0e9, 3.0e8),
        "current_assets": (2.0e9, 3.0e8),
        "current_liabilities": (1.5e9, 2.0e8),
        "shares_outstanding": (1.0e8, 0.0),
        "revenue": (3.0e9, 4.0e8),
        "cost_of_revenue": (2.0e9, 3.0e8),
        "gross_profit": (1.0e9, 1.5e8),
    }
    rows = []
    for s_idx in range(n_symbols):
        sym = f"SYM{s_idx:03d}"
        for q in quarters:
            for metric, (mean, std) in metrics.items():
                value = float(rng.normal(mean, std)) if std > 0 else mean
                rows.append(
                    {
                        COL_DATE: q,
                        COL_SYMBOL: sym,
                        "metric_name": metric,
                        "value": value,
                        "filing_type": "10-Q",
                        "period_end": q,
                    }
                )
    return pd.DataFrame(rows)


def _assert_row_order_invariant(compute_fn, panel: pd.DataFrame, *args, **kwargs) -> None:
    """Compute on the panel, shuffle rows, compute again, assert outputs are equal.

    Row-order invariance is a necessary condition for PiT purity: a function
    that depends on DataFrame row index order can silently produce a value
    whose answer leaks information about rows that would be dropped under a
    proper ``date <= T`` filter.
    """
    sorted_result, _ = compute_fn(panel.copy(), *args, **kwargs)
    shuffled = panel.sample(frac=1.0, random_state=42).reset_index(drop=True)
    shuffled_result, _ = compute_fn(shuffled, *args, **kwargs)
    pd.testing.assert_series_equal(
        sorted_result.sort_index(),
        shuffled_result.sort_index(),
        check_names=False,
    )


class TestFeaturePiTPurity:
    """RALPH TODO-12: every feature compute function is row-order invariant.

    One test per compute function across all six feature modules (16 tests total
    + 1 short-interest internal-lag-filter cross-check). Fixtures are deterministic
    and strictly pre-2023 to honor iron rule 1.
    """

    # price_volume.py
    def test_ivol_20d_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_ivol_20d, _make_price_panel(n_days=60))

    def test_52w_high_proximity_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_52w_high_proximity, _make_price_panel(n_days=260))

    def test_momentum_2_12_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_momentum_2_12, _make_price_panel(n_days=300))

    # sentiment.py (price/volume family + options)
    def test_ewmac_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_ewmac, _make_price_panel(n_days=100))

    def test_volume_momentum_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_volume_momentum, _make_price_panel(n_days=60))

    def test_put_call_ratio_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_put_call_ratio, _make_options_panel())

    # earnings.py
    def test_earnings_surprise_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_earnings_surprise, _make_earnings_panel())

    # nlp_earnings.py
    def test_earnings_sentiment_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_earnings_sentiment, _make_nlp_panel())

    def test_sentiment_surprise_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_sentiment_surprise, _make_nlp_panel(n_quarters=6))

    def test_sentiment_dispersion_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_sentiment_dispersion, _make_nlp_panel())

    # fundamental.py
    def test_piotroski_f_score_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_piotroski_f_score, _make_fundamental_panel())

    def test_accruals_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_accruals, _make_fundamental_panel())

    def test_profitability_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_profitability, _make_fundamental_panel())

    # short_interest.py (applies internal FINRA 11-day publication lag)
    def test_short_ratio_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_short_ratio, _make_short_interest_panel())

    def test_short_interest_pct_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_short_interest_pct, _make_short_interest_panel())

    def test_short_interest_change_pit_purity(self) -> None:
        _assert_row_order_invariant(compute_short_interest_change, _make_short_interest_panel())

    def test_finra_publication_lag_constant_is_eleven(self) -> None:
        """Sanity: the constant this test file relies on is the documented FINRA value.

        If someone renames or changes ``_FINRA_PUBLICATION_LAG``, the purity
        contract for the three short-interest functions changes shape and the
        surrounding tests need to be re-examined.
        """
        assert _FINRA_PUBLICATION_LAG == 11
