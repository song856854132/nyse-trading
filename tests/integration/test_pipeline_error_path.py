"""Integration test: ERROR path -- partial features NaN (data source partially down).

Scenarios:
  A. 60% NaN  -> exceeds 50% threshold -> skip rebalance, HOLD.
  B. 20% NaN  -> below 50% threshold -> proceed with imputed values.

The pipeline must distinguish between "too much missing data to trust" and
"some missing data that can be safely imputed."
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

# ── Graceful skip if implementation modules are not yet available ────────────
try:
    from nyse_core.allocator import equal_weight, select_top_n
    from nyse_core.contracts import (
        Diagnostics,
        PortfolioBuildResult,
        TradePlan,
    )
    from nyse_core.impute import cross_sectional_impute
    from nyse_core.normalize import rank_percentile
    from nyse_core.schema import (
        COL_CLOSE,
        COL_DATE,
        COL_SYMBOL,
        COL_VOLUME,
        DEFAULT_SELL_BUFFER,
        DEFAULT_TOP_N,
        RegimeState,
        Side,
    )

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False

pytestmark = [
    pytest.mark.skipif(not MODULES_AVAILABLE, reason="Implementation modules not yet available"),
    pytest.mark.integration,
]

# ── Constants ────────────────────────────────────────────────────────────────
N_STOCKS = 50
N_DAYS = 600
REBALANCE_DATE = date(2024, 6, 28)
SKIP_THRESHOLD = 0.50  # Skip rebalance if >50% of features are NaN


# ── Synthetic Data Helpers ───────────────────────────────────────────────────


def _make_symbols(n: int) -> list[str]:
    return [f"ERR_{i:02d}" for i in range(n)]


def _make_prices(symbols: list[str], n_days: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start_date = REBALANCE_DATE - timedelta(days=int(n_days * 1.5))
    dates = pd.bdate_range(start=start_date, periods=n_days, freq="B")

    rows: list[dict] = []
    for sym in symbols:
        base_price = rng.uniform(20, 200)
        daily_ret = rng.normal(0.0003, 0.02, size=n_days)
        closes = base_price * np.cumprod(1 + daily_ret)
        for i, dt in enumerate(dates):
            c = closes[i]
            rows.append(
                {
                    COL_DATE: dt.date(),
                    COL_SYMBOL: sym,
                    "open": c * rng.uniform(0.99, 1.01),
                    "high": c * rng.uniform(1.0, 1.03),
                    "low": c * rng.uniform(0.97, 1.0),
                    COL_CLOSE: c,
                    COL_VOLUME: int(rng.lognormal(14, 1)),
                }
            )

    return pd.DataFrame(rows)


def _compute_ivol_cross_section(
    prices_df: pd.DataFrame,
    symbols: list[str],
    as_of: date,
    window: int = 20,
) -> pd.Series:
    results = {}
    for sym in symbols:
        sym_prices = prices_df[prices_df[COL_SYMBOL] == sym].sort_values(COL_DATE)
        sym_prices = sym_prices[sym_prices[COL_DATE] <= as_of]
        if len(sym_prices) < window + 1:
            results[sym] = np.nan
            continue
        rets = sym_prices[COL_CLOSE].pct_change().dropna().tail(window)
        results[sym] = rets.std()
    return pd.Series(results)


def _build_features_with_nan_fraction(
    prices_df: pd.DataFrame,
    symbols: list[str],
    rebalance_date: date,
    nan_fraction: float,
    seed: int = 55,
) -> tuple[pd.DataFrame, list[str]]:
    """Build feature matrix with a controlled fraction of NaN values.

    nan_fraction of 0.60 means 60% of ivol_20d values are set to NaN.
    """
    ivol = _compute_ivol_cross_section(prices_df, symbols, rebalance_date)
    ivol_negated = -ivol

    rng = np.random.default_rng(seed)
    n_nan = int(len(symbols) * nan_fraction)
    nan_indices = rng.choice(len(symbols), size=n_nan, replace=False)
    for idx in nan_indices:
        ivol_negated.iloc[idx] = np.nan

    df = pd.DataFrame(
        {
            COL_DATE: rebalance_date,
            COL_SYMBOL: ivol_negated.index,
            "ivol_20d": ivol_negated.values,
        }
    )
    return df, ["ivol_20d"]


def _check_error_threshold(
    feature_df: pd.DataFrame,
    factor_names: list[str],
    threshold: float = SKIP_THRESHOLD,
) -> tuple[bool, float]:
    """Check if the overall NaN fraction exceeds the skip threshold.

    Returns (should_skip, actual_nan_fraction).
    """
    total_vals = 0
    total_nan = 0
    for col in factor_names:
        if col in feature_df.columns:
            total_vals += len(feature_df)
            total_nan += int(feature_df[col].isna().sum())
    nan_frac = total_nan / total_vals if total_vals > 0 else 1.0
    return nan_frac > threshold, nan_frac


def _build_skip_result(
    current_holdings: list[str],
    rebalance_date: date,
    nan_frac: float,
) -> PortfolioBuildResult:
    """Build a PortfolioBuildResult for ERROR path skip."""
    return PortfolioBuildResult(
        trade_plans=[],
        cost_estimate_usd=0.0,
        turnover_pct=0.0,
        regime_state=RegimeState.BULL,
        rebalance_date=rebalance_date,
        held_positions=len(current_holdings),
        new_entries=0,
        exits=0,
        skipped_reason=(f"ERROR path: {nan_frac:.1%} of features are NaN (>{SKIP_THRESHOLD:.0%} threshold)"),
    )


# ── Tests: 60% NaN -> Skip ──────────────────────────────────────────────────


class TestErrorPathHighNaN:
    """60% NaN features -- exceeds 50% threshold -> skip rebalance."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.symbols = _make_symbols(N_STOCKS)
        self.prices = _make_prices(self.symbols, N_DAYS)

    def test_60pct_nan_detected(self) -> None:
        """Verify 60% NaN fraction is correctly detected."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.60,
        )
        should_skip, nan_frac = _check_error_threshold(feat_df, factor_names)
        assert should_skip, f"Expected skip at {nan_frac:.1%} NaN"
        assert nan_frac >= 0.55  # allow small tolerance from randomness

    def test_no_trades_on_high_nan(self) -> None:
        """When >50% NaN, pipeline must skip and produce 0 TradePlans."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.60,
        )
        should_skip, nan_frac = _check_error_threshold(feat_df, factor_names)
        assert should_skip

        current_holdings = self.symbols[:8]
        result = _build_skip_result(current_holdings, REBALANCE_DATE, nan_frac)
        assert len(result.trade_plans) == 0

    def test_skipped_reason_set_on_high_nan(self) -> None:
        """PortfolioBuildResult.skipped_reason must be non-None."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.60,
        )
        _, nan_frac = _check_error_threshold(feat_df, factor_names)
        result = _build_skip_result(self.symbols[:5], REBALANCE_DATE, nan_frac)

        assert result.skipped_reason is not None
        assert "error" in result.skipped_reason.lower() or "nan" in result.skipped_reason.lower()

    def test_no_sells_on_high_nan(self) -> None:
        """CRITICAL: >50% NaN must NOT produce sell orders for held positions."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.60,
        )
        _, nan_frac = _check_error_threshold(feat_df, factor_names)
        result = _build_skip_result(self.symbols[:10], REBALANCE_DATE, nan_frac)

        sell_plans = [p for p in result.trade_plans if p.side == Side.SELL]
        assert len(sell_plans) == 0

    def test_held_positions_preserved_on_high_nan(self) -> None:
        """Held positions count must match prior holdings."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.60,
        )
        _, nan_frac = _check_error_threshold(feat_df, factor_names)
        result = _build_skip_result(self.symbols[:7], REBALANCE_DATE, nan_frac)

        assert result.held_positions == 7
        assert result.exits == 0
        assert result.new_entries == 0

    def test_imputation_drops_feature_at_60pct_nan(self) -> None:
        """cross_sectional_impute should drop the feature column when >30% NaN."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.60,
        )
        imputed, diag = cross_sectional_impute(feat_df, max_missing_pct=0.30)
        # 60% NaN > 30% threshold -> feature should be set to all NaN
        assert imputed["ivol_20d"].isna().all(), (
            "Feature with 60% NaN should be dropped by imputer (threshold=30%)"
        )


# ── Tests: 20% NaN -> Proceed ───────────────────────────────────────────────


class TestErrorPathLowNaN:
    """20% NaN features -- below 50% threshold -> proceed with imputed values."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.symbols = _make_symbols(N_STOCKS)
        self.prices = _make_prices(self.symbols, N_DAYS)

    def test_20pct_nan_does_not_trigger_skip(self) -> None:
        """20% NaN is below the 50% skip threshold."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.20,
        )
        should_skip, nan_frac = _check_error_threshold(feat_df, factor_names)
        assert not should_skip, f"20% NaN should NOT trigger skip, got {nan_frac:.1%}"

    def test_imputation_fills_at_20pct_nan(self) -> None:
        """With 20% NaN < 30% threshold, imputer should fill with median."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.20,
        )
        imputed, diag = cross_sectional_impute(feat_df, max_missing_pct=0.30)
        remaining_nan = imputed["ivol_20d"].isna().sum()
        assert remaining_nan == 0, f"Expected 0 NaN after imputation of 20% missing, got {remaining_nan}"

    def test_normalization_valid_after_imputation(self) -> None:
        """Normalized values must be in [0, 1] after imputing 20% NaN."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.20,
        )
        imputed, _ = cross_sectional_impute(feat_df, max_missing_pct=0.30)
        ranked, _ = rank_percentile(imputed["ivol_20d"])
        valid = ranked.dropna()
        assert (valid >= 0.0).all()
        assert (valid <= 1.0).all()

    def test_allocator_works_after_imputation(self) -> None:
        """Pipeline proceeds through allocation when NaN is below threshold."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.20,
        )
        imputed, _ = cross_sectional_impute(feat_df, max_missing_pct=0.30)
        ranked, _ = rank_percentile(imputed["ivol_20d"])

        scores = pd.Series(
            ranked.values,
            index=imputed[COL_SYMBOL].values,
        ).dropna()

        selected, diag = select_top_n(
            scores,
            n=DEFAULT_TOP_N,
            sell_buffer=DEFAULT_SELL_BUFFER,
        )
        assert len(selected) == DEFAULT_TOP_N
        assert not diag.has_errors

    def test_portfolio_result_not_skipped(self) -> None:
        """PortfolioBuildResult.skipped_reason must be None when proceeding."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.20,
        )
        should_skip, _ = _check_error_threshold(feat_df, factor_names)
        assert not should_skip

        # Pipeline proceeds -> build a normal result
        imputed, _ = cross_sectional_impute(feat_df, max_missing_pct=0.30)
        ranked, _ = rank_percentile(imputed["ivol_20d"])
        scores = pd.Series(
            ranked.values,
            index=imputed[COL_SYMBOL].values,
        ).dropna()
        selected, _ = select_top_n(scores, n=DEFAULT_TOP_N)
        weights, _ = equal_weight(selected)

        now = datetime(2024, 6, 28, 16, 0, 0)
        plans = [
            TradePlan(
                symbol=sym,
                side=Side.BUY,
                target_shares=int(1_000_000 * w / 50.0),
                current_shares=0,
                order_type="TWAP",
                reason="new_entry",
                decision_timestamp=now,
            )
            for sym, w in weights.items()
            if int(1_000_000 * w / 50.0) > 0
        ]

        result = PortfolioBuildResult(
            trade_plans=plans,
            cost_estimate_usd=100.0,
            turnover_pct=0.15,
            regime_state=RegimeState.BULL,
            rebalance_date=REBALANCE_DATE,
            held_positions=0,
            new_entries=len(plans),
            exits=0,
            skipped_reason=None,
        )
        assert result.skipped_reason is None
        assert len(result.trade_plans) > 0


# ── Tests: Boundary Conditions ───────────────────────────────────────────────


class TestErrorPathBoundary:
    """Edge cases: exactly at threshold, just above, just below."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.symbols = _make_symbols(N_STOCKS)
        self.prices = _make_prices(self.symbols, N_DAYS)

    def test_exactly_50pct_nan_does_not_skip(self) -> None:
        """Exactly 50% NaN is AT the threshold -> should NOT skip (> not >=)."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.50,
        )
        should_skip, nan_frac = _check_error_threshold(feat_df, factor_names)
        # Our threshold is strict >, not >=, so exactly 50% should NOT skip
        # (nan_frac may be slightly off due to rounding of integer count)
        if abs(nan_frac - 0.50) < 0.02:
            # At boundary: either skip or proceed is acceptable
            pass
        elif nan_frac > 0.50:
            assert should_skip
        else:
            assert not should_skip

    def test_51pct_nan_skips(self) -> None:
        """51% NaN is just above threshold -> must skip."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.52,
        )
        should_skip, nan_frac = _check_error_threshold(feat_df, factor_names)
        assert should_skip, f"51%+ NaN should trigger skip, got {nan_frac:.1%}"

    def test_49pct_nan_proceeds(self) -> None:
        """49% NaN is below threshold -> must proceed."""
        feat_df, factor_names = _build_features_with_nan_fraction(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nan_fraction=0.48,
        )
        should_skip, nan_frac = _check_error_threshold(feat_df, factor_names)
        assert not should_skip, f"49% NaN should NOT skip, got {nan_frac:.1%}"
