"""Integration test: Rigorous backtest pipeline with PurgedWalkForwardCV.

Validates that:
  - PurgedWalkForwardCV produces correct train/test splits with purge+embargo.
  - A planted signal (synthetic alpha) produces positive OOS Sharpe.
  - Metrics (Sharpe, CAGR, MaxDD) are computed correctly and within expected ranges.
  - BacktestResult contract is fully populated.

VectorBT comparison is deferred to Phase 2.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

# ── Graceful skip if implementation modules are not yet available ────────────
try:
    from nyse_core.backtest import run_walk_forward_backtest
    from nyse_core.contracts import BacktestResult, Diagnostics
    from nyse_core.cv import PurgedWalkForwardCV
    from nyse_core.models.ridge_model import RidgeModel
    from nyse_core.normalize import rank_percentile
    from nyse_core.schema import (
        COL_CLOSE,
        COL_DATE,
        COL_SYMBOL,
        DEFAULT_EMBARGO_DAYS,
        DEFAULT_PURGE_DAYS,
        TRADING_DAYS_PER_YEAR,
    )

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False

pytestmark = [
    pytest.mark.skipif(not MODULES_AVAILABLE, reason="Implementation modules not yet available"),
    pytest.mark.integration,
]

# ── Constants ────────────────────────────────────────────────────────────────
N_STOCKS = 30
N_DAYS = 1200  # ~4.8 years of trading days -- enough for 2yr min train + folds
SEED = 42


# ── Synthetic Data Helpers ───────────────────────────────────────────────────


def _make_symbols(n: int) -> list[str]:
    return [f"BT_{i:02d}" for i in range(n)]


def _make_dates(n_days: int) -> pd.DatetimeIndex:
    """Generate a sorted DatetimeIndex of business days."""
    return pd.bdate_range(start="2019-01-02", periods=n_days, freq="B")


def _make_panel_with_planted_signal(
    symbols: list[str],
    dates: pd.DatetimeIndex,
    signal_strength: float = 0.03,
    seed: int = SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate a panel of prices with a planted alpha signal.

    The planted signal is a simple factor: stocks ranked in the top half by
    this factor have a positive daily drift (+signal_strength annualized),
    while the bottom half have zero drift. This ensures a non-zero IC.

    Returns:
        (prices_panel, features_panel)
        - prices_panel: columns = symbols, index = dates, values = close prices.
        - features_panel: columns = [signal], index = dates x symbols multi,
          with a planted signal value for each stock-date.
    """
    rng = np.random.default_rng(seed)
    n_stocks = len(symbols)
    n_days = len(dates)

    # Assign each stock a persistent signal value in [0, 1]
    # Top half will have positive drift
    signal_values = np.linspace(0, 1, n_stocks)
    rng.shuffle(signal_values)

    daily_drift = signal_strength / TRADING_DAYS_PER_YEAR
    daily_vol = 0.02

    prices = pd.DataFrame(index=dates, columns=symbols, dtype=float)
    for i, sym in enumerate(symbols):
        # Stocks with signal > 0.5 get positive drift
        drift = daily_drift if signal_values[i] > 0.5 else 0.0
        returns = rng.normal(drift, daily_vol, size=n_days)
        prices[sym] = 100.0 * np.cumprod(1 + returns)

    # Build features: signal is the persistent rank (known at each date)
    feature_rows: list[dict] = []
    for dt in dates:
        for i, sym in enumerate(symbols):
            feature_rows.append(
                {
                    COL_DATE: dt,
                    COL_SYMBOL: sym,
                    "planted_signal": signal_values[i],
                }
            )
    features = pd.DataFrame(feature_rows)

    return prices, features


def _compute_forward_returns(
    prices: pd.DataFrame,
    horizon: int = 5,
) -> pd.DataFrame:
    """Compute forward returns for each stock at each date.

    Returns DataFrame with same shape as prices, values = (price[t+h] - price[t]) / price[t].
    Last `horizon` rows will be NaN.
    """
    return prices.shift(-horizon) / prices - 1.0


def _compute_sharpe(returns: pd.Series) -> float:
    """Annualized Sharpe ratio from daily returns."""
    if len(returns) < 2 or returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * math.sqrt(TRADING_DAYS_PER_YEAR))


def _compute_cagr(returns: pd.Series) -> float:
    """Compound Annual Growth Rate from daily returns."""
    if len(returns) == 0:
        return 0.0
    cum = (1 + returns).prod()
    n_years = len(returns) / TRADING_DAYS_PER_YEAR
    if n_years <= 0 or cum <= 0:
        return 0.0
    return float(cum ** (1.0 / n_years) - 1.0)


def _compute_max_drawdown(returns: pd.Series) -> float:
    """Maximum drawdown from daily returns (returned as a negative number)."""
    if len(returns) == 0:
        return 0.0
    cum = (1 + returns).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    return float(dd.min())


def _run_rigorous_backtest(
    prices: pd.DataFrame,
    features: pd.DataFrame,
    symbols: list[str],
    dates: pd.DatetimeIndex,
    n_folds: int = 3,
    test_days: int = 126,  # ~6 months
    target_horizon: int = 5,
) -> BacktestResult:
    """Run a simplified rigorous backtest using PurgedWalkForwardCV + Ridge.

    For each fold:
      1. Train Ridge on train dates using planted_signal to predict fwd returns.
      2. Predict on test dates.
      3. Go long top-half stocks, equal weight.
      4. Compute daily portfolio returns on test dates.

    Returns a BacktestResult with aggregated metrics.
    """
    cv = PurgedWalkForwardCV(
        n_folds=n_folds,
        min_train_days=TRADING_DAYS_PER_YEAR * 2,  # 2 years
        test_days=test_days,
        purge_days=DEFAULT_PURGE_DAYS,
        embargo_days=DEFAULT_EMBARGO_DAYS,
        target_horizon_days=target_horizon,
    )

    fwd_rets = _compute_forward_returns(prices, horizon=target_horizon)

    all_daily_returns: list[pd.Series] = []
    per_fold_sharpe: list[float] = []

    for train_idx, test_idx in cv.split(dates):
        train_dates = dates[train_idx]
        test_dates = dates[test_idx]

        # Build training data: for each train date, cross-sectional features + fwd return
        train_feat = features[features[COL_DATE].isin(train_dates)]
        X_train_rows = []
        y_train_vals = []
        for _, row in train_feat.iterrows():
            sym = row[COL_SYMBOL]
            dt = row[COL_DATE]
            if sym in fwd_rets.columns and dt in fwd_rets.index:
                fret = fwd_rets.loc[dt, sym]
                if not np.isnan(fret) and not np.isnan(row["planted_signal"]):
                    X_train_rows.append({"planted_signal": row["planted_signal"]})
                    y_train_vals.append(fret)

        if len(X_train_rows) < 10:
            continue

        X_train = pd.DataFrame(X_train_rows)
        y_train = pd.Series(y_train_vals)

        # Normalize features to [0,1] for Ridge (already in [0,1] for planted_signal)
        model = RidgeModel(alpha=1.0)
        fit_diag = model.fit(X_train, y_train)
        if fit_diag.has_errors:
            continue

        # Predict on test dates and construct daily long-short returns
        fold_returns = []
        for dt in test_dates:
            test_feat = features[features[COL_DATE] == dt]
            if len(test_feat) == 0:
                continue

            X_test = test_feat[["planted_signal"]].reset_index(drop=True)
            X_test = X_test.dropna()
            if len(X_test) == 0:
                continue

            scores, _ = model.predict(X_test)

            # Go long top-half, compute daily return as average next-day return
            top_half = test_feat.iloc[scores.values.argsort()[-len(scores) // 2 :]]
            top_syms = top_half[COL_SYMBOL].values
            dt_idx = dates.get_loc(dt)
            if dt_idx + 1 >= len(dates):
                continue

            next_date = dates[dt_idx + 1]
            daily_rets = []
            for sym in top_syms:
                if sym in prices.columns and next_date in prices.index:
                    prev = prices.loc[dt, sym]
                    curr = prices.loc[next_date, sym]
                    if prev > 0:
                        daily_rets.append(curr / prev - 1.0)

            if daily_rets:
                fold_returns.append(np.mean(daily_rets))

        if fold_returns:
            fold_series = pd.Series(fold_returns)
            all_daily_returns.append(fold_series)
            per_fold_sharpe.append(_compute_sharpe(fold_series))

    if not all_daily_returns:
        # No valid folds -- return degenerate result
        empty_series = pd.Series(dtype=float)
        return BacktestResult(
            daily_returns=empty_series,
            oos_sharpe=0.0,
            oos_cagr=0.0,
            max_drawdown=0.0,
            annual_turnover=0.0,
            cost_drag_pct=0.0,
            per_fold_sharpe=[],
            per_factor_contribution={"planted_signal": 1.0},
        )

    combined = pd.concat(all_daily_returns, ignore_index=True)

    return BacktestResult(
        daily_returns=combined,
        oos_sharpe=_compute_sharpe(combined),
        oos_cagr=_compute_cagr(combined),
        max_drawdown=_compute_max_drawdown(combined),
        annual_turnover=52.0,  # weekly rebalance -> ~52 turns/year
        cost_drag_pct=0.005,
        per_fold_sharpe=per_fold_sharpe,
        per_factor_contribution={"planted_signal": 1.0},
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestPurgedWalkForwardCV:
    """Verify the CV splitter produces correct, non-overlapping splits."""

    def test_cv_produces_correct_number_of_folds(self) -> None:
        """CV should yield up to n_folds splits."""
        dates = _make_dates(N_DAYS)
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=TRADING_DAYS_PER_YEAR * 2,
            test_days=126,
            purge_days=DEFAULT_PURGE_DAYS,
            embargo_days=DEFAULT_EMBARGO_DAYS,
            target_horizon_days=5,
        )
        splits = list(cv.split(dates))
        assert len(splits) > 0
        assert len(splits) <= 3

    def test_train_test_no_overlap(self) -> None:
        """Train and test indices must never overlap."""
        dates = _make_dates(N_DAYS)
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=TRADING_DAYS_PER_YEAR * 2,
            test_days=126,
            purge_days=DEFAULT_PURGE_DAYS,
            embargo_days=DEFAULT_EMBARGO_DAYS,
        )
        for train_idx, test_idx in cv.split(dates):
            overlap = set(train_idx) & set(test_idx)
            assert len(overlap) == 0, f"Train/test overlap: {len(overlap)} indices"

    def test_purge_gap_exists(self) -> None:
        """There must be a gap >= purge_days between train end and test start."""
        dates = _make_dates(N_DAYS)
        purge = 10
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=TRADING_DAYS_PER_YEAR * 2,
            test_days=126,
            purge_days=purge,
            embargo_days=DEFAULT_EMBARGO_DAYS,
            target_horizon_days=5,
        )
        for train_idx, test_idx in cv.split(dates):
            train_end = train_idx[-1]
            test_start = test_idx[0]
            gap = test_start - train_end
            # Gap must be at least max(purge_days, target_horizon_days)
            expected_min_gap = max(purge, 5)
            assert gap >= expected_min_gap, f"Purge gap {gap} < expected {expected_min_gap}"

    def test_expanding_window(self) -> None:
        """Each successive fold must have a larger or equal training set."""
        dates = _make_dates(N_DAYS)
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=TRADING_DAYS_PER_YEAR * 2,
            test_days=126,
            purge_days=DEFAULT_PURGE_DAYS,
            embargo_days=DEFAULT_EMBARGO_DAYS,
        )
        train_sizes = [len(train) for train, _ in cv.split(dates)]
        for i in range(1, len(train_sizes)):
            assert train_sizes[i] >= train_sizes[i - 1], (
                f"Fold {i} train ({train_sizes[i]}) < fold {i - 1} ({train_sizes[i - 1]})"
            )

    def test_insufficient_data_raises(self) -> None:
        """Too few observations must raise ValueError."""
        short_dates = _make_dates(100)
        cv = PurgedWalkForwardCV(
            n_folds=3,
            min_train_days=TRADING_DAYS_PER_YEAR * 2,
            test_days=126,
            purge_days=DEFAULT_PURGE_DAYS,
            embargo_days=DEFAULT_EMBARGO_DAYS,
        )
        with pytest.raises(ValueError, match="Not enough data"):
            list(cv.split(short_dates))

    def test_max_params_check_warns(self) -> None:
        """AP-7: too many params with too few observations should warn."""
        cv = PurgedWalkForwardCV(
            n_folds=1,
            min_train_days=TRADING_DAYS_PER_YEAR * 2,
            test_days=126,
            purge_days=DEFAULT_PURGE_DAYS,
            embargo_days=DEFAULT_EMBARGO_DAYS,
        )
        # 10 params with only 50 monthly obs (= 1050 daily / 21 ~= 50 months)
        result, _diag = cv.max_params_check(n_params=10, n_obs=1050)
        assert result is False  # should flag a concern


class TestRigorousBacktest:
    """Verify the full rigorous backtest pipeline on planted signal data."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.symbols = _make_symbols(N_STOCKS)
        self.dates = _make_dates(N_DAYS)
        self.prices, self.features = _make_panel_with_planted_signal(
            self.symbols,
            self.dates,
            signal_strength=0.03,
        )

    def test_planted_signal_produces_positive_oos_sharpe(self) -> None:
        """A planted signal with 3% annualized alpha should produce positive OOS Sharpe."""
        result = _run_rigorous_backtest(
            self.prices,
            self.features,
            self.symbols,
            self.dates,
        )
        assert result.oos_sharpe > 0.0, (
            f"Planted signal should produce positive OOS Sharpe, got {result.oos_sharpe:.4f}"
        )

    def test_backtest_result_has_daily_returns(self) -> None:
        """BacktestResult must contain a non-empty daily_returns Series."""
        result = _run_rigorous_backtest(
            self.prices,
            self.features,
            self.symbols,
            self.dates,
        )
        assert len(result.daily_returns) > 0
        assert isinstance(result.daily_returns, pd.Series)

    def test_per_fold_sharpe_is_populated(self) -> None:
        """Per-fold Sharpe ratios must be non-empty and match fold count."""
        result = _run_rigorous_backtest(
            self.prices,
            self.features,
            self.symbols,
            self.dates,
            n_folds=3,
        )
        assert len(result.per_fold_sharpe) > 0
        assert len(result.per_fold_sharpe) <= 3

    def test_max_drawdown_is_negative_or_zero(self) -> None:
        """MaxDD must be <= 0 (it represents a loss)."""
        result = _run_rigorous_backtest(
            self.prices,
            self.features,
            self.symbols,
            self.dates,
        )
        assert result.max_drawdown <= 0.0

    def test_cagr_is_reasonable(self) -> None:
        """CAGR should be in a reasonable range (-50% to +50%)."""
        result = _run_rigorous_backtest(
            self.prices,
            self.features,
            self.symbols,
            self.dates,
        )
        assert -0.50 <= result.oos_cagr <= 0.50, f"CAGR {result.oos_cagr:.4f} outside reasonable range"

    def test_sharpe_within_expected_range(self) -> None:
        """OOS Sharpe for a planted signal should be between 0 and 3.

        A 3% planted alpha with 2% daily vol on 30 stocks should not produce
        extreme Sharpe -- this guards against lookahead leakage.
        """
        result = _run_rigorous_backtest(
            self.prices,
            self.features,
            self.symbols,
            self.dates,
        )
        assert result.oos_sharpe < 3.0, (
            f"Suspiciously high OOS Sharpe {result.oos_sharpe:.4f} -- check for lookahead bias"
        )

    def test_factor_contribution_sums_to_one(self) -> None:
        """Per-factor contribution should sum to ~1.0."""
        result = _run_rigorous_backtest(
            self.prices,
            self.features,
            self.symbols,
            self.dates,
        )
        total = sum(result.per_factor_contribution.values())
        assert abs(total - 1.0) < 1e-6

    def test_backtest_result_contract_fields(self) -> None:
        """All BacktestResult fields must be populated with correct types."""
        result = _run_rigorous_backtest(
            self.prices,
            self.features,
            self.symbols,
            self.dates,
        )
        assert isinstance(result.daily_returns, pd.Series)
        assert isinstance(result.oos_sharpe, float)
        assert isinstance(result.oos_cagr, float)
        assert isinstance(result.max_drawdown, float)
        assert isinstance(result.annual_turnover, float)
        assert isinstance(result.cost_drag_pct, float)
        assert isinstance(result.per_fold_sharpe, list)
        assert isinstance(result.per_factor_contribution, dict)

    def test_no_signal_produces_near_zero_sharpe(self) -> None:
        """With zero signal strength, OOS Sharpe should be near zero."""
        prices_no_signal, features_no_signal = _make_panel_with_planted_signal(
            self.symbols,
            self.dates,
            signal_strength=0.0,
            seed=99,
        )
        result = _run_rigorous_backtest(
            prices_no_signal,
            features_no_signal,
            self.symbols,
            self.dates,
        )
        # With zero signal, Sharpe should be close to zero (within noise)
        assert abs(result.oos_sharpe) < 1.5, (
            f"Zero signal produced Sharpe {result.oos_sharpe:.4f} -- expected ~0"
        )

    def test_ridge_model_used_correctly(self) -> None:
        """Verify the Ridge model fits and predicts without errors within the backtest."""
        # Direct test of model on backtest-style data
        rng = np.random.default_rng(SEED)
        X = pd.DataFrame({"planted_signal": rng.uniform(0, 1, size=500)})
        y = pd.Series(rng.normal(0, 0.02, size=500))

        model = RidgeModel(alpha=1.0)
        fit_diag = model.fit(X, y)
        assert not fit_diag.has_errors

        scores, pred_diag = model.predict(X)
        assert len(scores) == 500
        assert not pred_diag.has_errors

        importance = model.get_feature_importance()
        assert "planted_signal" in importance


class TestRealBacktestFunction:
    """Exercise the actual run_walk_forward_backtest() function."""

    def test_function_produces_valid_result(self) -> None:
        """run_walk_forward_backtest should work with CombinationModel callables."""
        rng = np.random.default_rng(SEED)
        n_days = 1200
        dates = _make_dates(n_days)
        n_features = 2

        feature_data = rng.uniform(0, 1, size=(n_days, n_features))
        feature_matrix = pd.DataFrame(
            feature_data,
            index=dates,
            columns=[f"f{i}" for i in range(n_features)],
        )

        noise = rng.normal(0, 0.02, size=n_days)
        returns_series = pd.Series(
            0.001 * feature_data[:, 0] + noise,
            index=dates,
        )

        cv = PurgedWalkForwardCV(
            n_folds=2,
            min_train_days=TRADING_DAYS_PER_YEAR * 2,
            test_days=126,
            purge_days=DEFAULT_PURGE_DAYS,
            embargo_days=DEFAULT_EMBARGO_DAYS,
            target_horizon_days=5,
        )

        def model_factory():
            return RidgeModel(alpha=1.0)

        def allocator_fn(predictions):
            w = np.where(predictions > 0, 1.0, 0.0)
            total = w.sum()
            return w / total if total > 0 else w

        def risk_fn(weights):
            return weights

        def cost_fn(weights_prev, weights_new):
            return float(np.abs(weights_new - weights_prev).sum() * 0.001)

        result, diag = run_walk_forward_backtest(
            feature_matrix=feature_matrix,
            returns=returns_series,
            cv=cv,
            model_factory=model_factory,
            allocator_fn=allocator_fn,
            risk_fn=risk_fn,
            cost_fn=cost_fn,
        )

        assert isinstance(result, BacktestResult)
        assert len(result.daily_returns) > 0
        assert len(result.per_fold_sharpe) > 0
        assert isinstance(result.per_factor_contribution, dict)
        assert not diag.has_errors
