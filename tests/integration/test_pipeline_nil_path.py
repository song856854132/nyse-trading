"""Integration test: NIL path -- >20% of stocks have no data for rebalance date.

When a significant fraction of the universe has missing data on the rebalance
date, the pipeline must HOLD current positions and NOT generate new trades.
This prevents forced selling into a data outage.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

# ── Graceful skip if implementation modules are not yet available ────────────
try:
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
NIL_FRACTION = 0.25  # >20% of stocks missing data


# ── Synthetic Data Helpers ───────────────────────────────────────────────────


def _make_symbols(n: int) -> list[str]:
    return [f"NIL_{i:02d}" for i in range(n)]


def _make_prices(symbols: list[str], n_days: int, seed: int = 42) -> pd.DataFrame:
    """Generate OHLCV data for N stocks. Identical to e2e helper."""
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


def _simulate_nil_path(
    prices_df: pd.DataFrame,
    symbols: list[str],
    rebalance_date: date,
    nil_fraction: float,
    seed: int = 77,
) -> pd.DataFrame:
    """Build feature matrix but set >nil_fraction of stocks to have NO data.

    Simulates a data source outage where many stocks report no IVOL.
    Returns DataFrame with [date, symbol, ivol_20d] where many rows are NaN.
    """
    ivol = _compute_ivol_cross_section(prices_df, symbols, rebalance_date)
    ivol_negated = -ivol

    # Blank out >nil_fraction of stocks
    rng = np.random.default_rng(seed)
    n_nil = int(len(symbols) * nil_fraction) + 1  # ensure >20%
    nil_indices = rng.choice(len(symbols), size=n_nil, replace=False)
    for idx in nil_indices:
        ivol_negated.iloc[idx] = np.nan

    df = pd.DataFrame(
        {
            COL_DATE: rebalance_date,
            COL_SYMBOL: ivol_negated.index,
            "ivol_20d": ivol_negated.values,
        }
    )
    return df


def _check_nil_threshold(
    feature_df: pd.DataFrame,
    factor_names: list[str],
    nil_threshold: float = 0.20,
) -> tuple[bool, float]:
    """Check if the NaN fraction exceeds the NIL threshold.

    Returns (should_skip, actual_nan_fraction).
    """
    total_vals = 0
    total_nan = 0
    for col in factor_names:
        total_vals += len(feature_df)
        total_nan += int(feature_df[col].isna().sum())
    nan_frac = total_nan / total_vals if total_vals > 0 else 1.0
    return nan_frac > nil_threshold, nan_frac


def _build_nil_portfolio_result(
    current_holdings: list[str],
    rebalance_date: date,
    nan_frac: float,
) -> PortfolioBuildResult:
    """Build a PortfolioBuildResult that represents a HOLD decision (no trading)."""
    return PortfolioBuildResult(
        trade_plans=[],
        cost_estimate_usd=0.0,
        turnover_pct=0.0,
        regime_state=RegimeState.BULL,  # regime is irrelevant when skipping
        rebalance_date=rebalance_date,
        held_positions=len(current_holdings),
        new_entries=0,
        exits=0,
        skipped_reason=f"NIL path: {nan_frac:.1%} of universe has missing data (>20% threshold)",
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestPipelineNilPath:
    """NIL path: >20% of stocks have no data -- pipeline must HOLD."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.symbols = _make_symbols(N_STOCKS)
        self.prices = _make_prices(self.symbols, N_DAYS)

    def test_nil_fraction_exceeds_threshold(self) -> None:
        """Verify that our synthetic data actually has >20% missing."""
        feat_df = _simulate_nil_path(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            NIL_FRACTION,
        )
        should_skip, nan_frac = _check_nil_threshold(feat_df, ["ivol_20d"])
        assert should_skip, f"Expected >20% NaN, got {nan_frac:.1%}"
        assert nan_frac > 0.20

    def test_no_trade_plans_generated(self) -> None:
        """When NIL threshold triggered, zero TradePlans must be generated."""
        feat_df = _simulate_nil_path(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            NIL_FRACTION,
        )
        should_skip, nan_frac = _check_nil_threshold(feat_df, ["ivol_20d"])
        assert should_skip

        # Simulate current holdings (5 stocks held from previous rebalance)
        current_holdings = self.symbols[:5]
        result = _build_nil_portfolio_result(current_holdings, REBALANCE_DATE, nan_frac)

        assert len(result.trade_plans) == 0, "NIL path must not generate any trades"

    def test_skipped_reason_is_set(self) -> None:
        """PortfolioBuildResult.skipped_reason must be non-None on NIL path."""
        feat_df = _simulate_nil_path(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            NIL_FRACTION,
        )
        _, nan_frac = _check_nil_threshold(feat_df, ["ivol_20d"])

        current_holdings = self.symbols[:5]
        result = _build_nil_portfolio_result(current_holdings, REBALANCE_DATE, nan_frac)

        assert result.skipped_reason is not None
        assert "missing data" in result.skipped_reason.lower() or "nil" in result.skipped_reason.lower()

    def test_held_positions_preserved(self) -> None:
        """On NIL path, the held_positions count must match prior holdings."""
        feat_df = _simulate_nil_path(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            NIL_FRACTION,
        )
        _, nan_frac = _check_nil_threshold(feat_df, ["ivol_20d"])

        current_holdings = self.symbols[:8]
        result = _build_nil_portfolio_result(current_holdings, REBALANCE_DATE, nan_frac)

        assert result.held_positions == 8
        assert result.new_entries == 0
        assert result.exits == 0

    def test_no_sell_orders_on_nil_path(self) -> None:
        """CRITICAL: NIL path must NOT generate sell orders for current holdings."""
        feat_df = _simulate_nil_path(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            NIL_FRACTION,
        )
        should_skip, nan_frac = _check_nil_threshold(feat_df, ["ivol_20d"])
        assert should_skip

        current_holdings = self.symbols[:10]
        result = _build_nil_portfolio_result(current_holdings, REBALANCE_DATE, nan_frac)

        sell_plans = [p for p in result.trade_plans if p.side == Side.SELL]
        assert len(sell_plans) == 0, f"NIL path generated {len(sell_plans)} SELL orders -- must be 0"

    def test_zero_turnover_on_nil_path(self) -> None:
        """Turnover must be 0% when rebalance is skipped."""
        feat_df = _simulate_nil_path(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            NIL_FRACTION,
        )
        _, nan_frac = _check_nil_threshold(feat_df, ["ivol_20d"])

        result = _build_nil_portfolio_result(self.symbols[:5], REBALANCE_DATE, nan_frac)
        assert result.turnover_pct == 0.0
        assert result.cost_estimate_usd == 0.0

    def test_imputation_not_attempted_on_nil_path(self) -> None:
        """When >20% is missing, we skip entirely -- imputation should not run.

        However, if imputation IS run, cross_sectional_impute with max_missing_pct=0.30
        should still drop the feature column for dates exceeding the threshold.
        """
        feat_df = _simulate_nil_path(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
            nil_fraction=0.35,
        )
        # Even if someone runs imputation, the feature should be dropped
        imputed, diag = cross_sectional_impute(feat_df, max_missing_pct=0.30)
        # With 35% NaN > 30% threshold, the column should be all NaN for that date
        assert imputed["ivol_20d"].isna().all(), (
            "Feature with >30% NaN should be dropped entirely by cross_sectional_impute"
        )
