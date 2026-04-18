"""Integration test: Happy-path end-to-end pipeline.

Generates 50 synthetic stocks over 600 trading days, then runs the full
pipeline: features -> normalize -> impute -> combine -> allocate -> regime
overlay -> caps -> TradePlan generation.

Verifies that all outputs satisfy the contracts defined in nyse_core.contracts.
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
        BacktestResult,
        CompositeScore,
        Diagnostics,
        FeatureMatrix,
        PortfolioBuildResult,
        TradePlan,
        UniverseSnapshot,
    )
    from nyse_core.cost_model import estimate_cost_bps
    from nyse_core.impute import cross_sectional_impute
    from nyse_core.models.ridge_model import RidgeModel
    from nyse_core.normalize import rank_percentile
    from nyse_core.schema import (
        BEAR_EXPOSURE,
        BULL_EXPOSURE,
        COL_CLOSE,
        COL_DATE,
        COL_SECTOR,
        COL_SYMBOL,
        COL_VOLUME,
        DEFAULT_SELL_BUFFER,
        DEFAULT_TOP_N,
        MAX_POSITION_PCT,
        MAX_SECTOR_PCT,
        TRADING_DAYS_PER_YEAR,
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
GICS_SECTORS = [
    "Information Technology",
    "Health Care",
    "Financials",
    "Consumer Discretionary",
    "Industrials",
]


# ── Synthetic Data Helpers ───────────────────────────────────────────────────


def _make_symbols(n: int) -> list[str]:
    """Generate deterministic ticker symbols: SYM_00 .. SYM_49."""
    return [f"SYM_{i:02d}" for i in range(n)]


def _make_prices(
    symbols: list[str],
    n_days: int,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic OHLCV data for *n* stocks over *n_days* trading days.

    Prices follow a geometric Brownian motion with a small positive drift so
    that the universe is not degenerate.  Volume is log-normal.
    """
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


def _make_sector_map(symbols: list[str], seed: int = 42) -> dict[str, str]:
    """Deterministic sector assignment, cycling through GICS_SECTORS."""
    np.random.default_rng(seed)
    return {sym: GICS_SECTORS[i % len(GICS_SECTORS)] for i, sym in enumerate(symbols)}


def _compute_ivol_cross_section(
    prices_df: pd.DataFrame,
    symbols: list[str],
    as_of: date,
    window: int = 20,
) -> pd.Series:
    """Compute 20-day IVOL for every symbol as of *as_of*.

    Returns a Series indexed by symbol with NaN where history is insufficient.
    """
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


def _build_feature_matrix(
    prices_df: pd.DataFrame,
    symbols: list[str],
    rebalance_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """Build a single-factor (IVOL) feature matrix for the rebalance date.

    Returns (DataFrame with columns [date, symbol, ivol_20d], factor_names).
    """
    ivol = _compute_ivol_cross_section(prices_df, symbols, rebalance_date)
    # IVOL sign: low-vol is good, so negate for rank ordering
    ivol_negated = -ivol
    df = pd.DataFrame(
        {
            COL_DATE: rebalance_date,
            COL_SYMBOL: ivol_negated.index,
            "ivol_20d": ivol_negated.values,
        }
    )
    return df, ["ivol_20d"]


def _normalize_features(
    feature_df: pd.DataFrame,
    factor_names: list[str],
) -> pd.DataFrame:
    """Rank-percentile normalize each factor column to [0, 1]."""
    result = feature_df.copy()
    for col in factor_names:
        ranked, _ = rank_percentile(result[col])
        result[col] = ranked
    return result


def _determine_regime(
    prices_df: pd.DataFrame,
    benchmark_sym: str,
    rebalance_date: date,
) -> RegimeState:
    """Simple SMA200 binary regime: BULL if last close > SMA200, else BEAR."""
    bench = prices_df[prices_df[COL_SYMBOL] == benchmark_sym].sort_values(COL_DATE)
    bench = bench[bench[COL_DATE] <= rebalance_date]
    if len(bench) < 200:
        return RegimeState.BULL  # default to BULL if insufficient history
    sma200 = bench[COL_CLOSE].tail(200).mean()
    last_close = bench[COL_CLOSE].iloc[-1]
    return RegimeState.BULL if last_close >= sma200 else RegimeState.BEAR


def _apply_caps(
    weights: dict[str, float],
    sector_map: dict[str, str],
    max_position: float = MAX_POSITION_PCT,
    max_sector: float = MAX_SECTOR_PCT,
) -> dict[str, float]:
    """Clip individual positions at max_position, sector totals at max_sector.

    Returns re-normalized weights that sum to ~1.0.
    """
    # Position cap
    capped = {sym: min(w, max_position) for sym, w in weights.items()}

    # Sector cap: pro-rata scale down sectors that exceed max_sector
    sector_totals: dict[str, float] = {}
    for sym, w in capped.items():
        sec = sector_map.get(sym, "Unknown")
        sector_totals[sec] = sector_totals.get(sec, 0.0) + w

    for sec, total in sector_totals.items():
        if total > max_sector:
            scale = max_sector / total
            for sym in capped:
                if sector_map.get(sym, "Unknown") == sec:
                    capped[sym] *= scale

    # Re-normalize to sum to 1.0
    total_w = sum(capped.values())
    if total_w > 0:
        capped = {sym: w / total_w for sym, w in capped.items()}

    return capped


def _generate_trade_plans(
    weights: dict[str, float],
    regime: RegimeState,
    portfolio_value: float = 1_000_000.0,
    avg_price: float = 50.0,
) -> list[TradePlan]:
    """Convert target weights into TradePlan objects.

    Applies regime exposure scaling (BULL=1.0, BEAR=0.4) to the weights.
    """
    exposure = BULL_EXPOSURE if regime == RegimeState.BULL else BEAR_EXPOSURE
    now = datetime(2024, 6, 28, 16, 0, 0)
    plans: list[TradePlan] = []

    for sym, w in weights.items():
        effective_w = w * exposure
        target_shares = int(portfolio_value * effective_w / avg_price)
        if target_shares == 0:
            continue
        plans.append(
            TradePlan(
                symbol=sym,
                side=Side.BUY,
                target_shares=target_shares,
                current_shares=0,
                order_type="TWAP",
                reason="new_entry",
                decision_timestamp=now,
            )
        )

    return plans


# ── Tests ────────────────────────────────────────────────────────────────────


class TestPipelineEndToEnd:
    """Happy-path: 50 stocks, 600 days, full pipeline through TradePlan generation."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        """Build the synthetic universe once for all tests in this class."""
        self.symbols = _make_symbols(N_STOCKS)
        self.prices = _make_prices(self.symbols, N_DAYS)
        self.sector_map = _make_sector_map(self.symbols)

    def test_synthetic_data_has_correct_shape(self) -> None:
        """Sanity check: synthetic data has N_STOCKS * N_DAYS rows."""
        expected_rows = N_STOCKS * N_DAYS
        assert len(self.prices) == expected_rows
        assert set(self.prices[COL_SYMBOL].unique()) == set(self.symbols)

    def test_feature_computation_produces_valid_output(self) -> None:
        """IVOL feature matrix has one row per stock, no all-NaN result."""
        feat_df, factor_names = _build_feature_matrix(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
        )
        assert len(feat_df) == N_STOCKS
        assert factor_names == ["ivol_20d"]
        # At most a few NaN from short history; not all NaN
        nan_frac = feat_df["ivol_20d"].isna().mean()
        assert nan_frac < 0.5, f"Too many NaN in IVOL: {nan_frac:.1%}"

    def test_normalization_maps_to_unit_interval(self) -> None:
        """Rank-percentile normalization produces values strictly in [0, 1]."""
        feat_df, factor_names = _build_feature_matrix(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
        )
        normed = _normalize_features(feat_df, factor_names)
        valid = normed["ivol_20d"].dropna()
        assert (valid >= 0.0).all(), "Normalized values below 0"
        assert (valid <= 1.0).all(), "Normalized values above 1"

    def test_imputation_fills_nan_with_median(self) -> None:
        """Cross-sectional imputation fills sparse NaN with median."""
        feat_df, factor_names = _build_feature_matrix(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
        )
        normed = _normalize_features(feat_df, factor_names)
        # Inject 10% NaN to simulate missing data
        rng = np.random.default_rng(99)
        mask = rng.random(len(normed)) < 0.10
        normed.loc[mask, "ivol_20d"] = np.nan

        imputed, diag = cross_sectional_impute(normed, max_missing_pct=0.30)
        # After imputation, NaN count should be 0 (below threshold)
        remaining_nan = imputed["ivol_20d"].isna().sum()
        assert remaining_nan == 0, f"Expected 0 NaN after imputation, got {remaining_nan}"

    def test_ridge_model_fit_and_predict(self) -> None:
        """Ridge model fits on normalized features and produces per-stock scores."""
        feat_df, factor_names = _build_feature_matrix(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
        )
        normed = _normalize_features(feat_df, factor_names)
        imputed, _ = cross_sectional_impute(normed, max_missing_pct=0.30)

        X = imputed[factor_names].dropna()
        # Synthetic target: forward 5-day return (random for contract test)
        rng = np.random.default_rng(123)
        y = pd.Series(rng.normal(0, 0.02, size=len(X)), index=X.index)

        model = RidgeModel(alpha=1.0)
        fit_diag = model.fit(X, y)
        assert not fit_diag.has_errors, f"Ridge fit errors: {fit_diag.messages}"

        scores, pred_diag = model.predict(X)
        assert len(scores) == len(X)
        assert not pred_diag.has_errors

        importance = model.get_feature_importance()
        assert "ivol_20d" in importance
        assert abs(sum(importance.values()) - 1.0) < 1e-6

    def test_allocator_selects_top_n(self) -> None:
        """Top-N allocator with sell_buffer selects exactly N stocks."""
        feat_df, factor_names = _build_feature_matrix(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
        )
        normed = _normalize_features(feat_df, factor_names)
        imputed, _ = cross_sectional_impute(normed, max_missing_pct=0.30)

        # Use normalized IVOL as composite score
        scores = pd.Series(
            imputed["ivol_20d"].values,
            index=imputed[COL_SYMBOL].values,
        ).dropna()

        selected, diag = select_top_n(
            scores,
            n=DEFAULT_TOP_N,
            sell_buffer=DEFAULT_SELL_BUFFER,
        )
        assert len(selected) == DEFAULT_TOP_N
        # All selected must be real symbols
        assert all(sym in self.symbols for sym in selected)

    def test_equal_weight_sums_to_one(self) -> None:
        """Equal weighting of N stocks produces weights summing to 1.0."""
        fake_selected = _make_symbols(DEFAULT_TOP_N)
        weights, diag = equal_weight(fake_selected)
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-10, f"Weights sum to {total}, expected 1.0"

    def test_position_cap_respected(self) -> None:
        """No individual position exceeds MAX_POSITION_PCT after capping."""
        fake_selected = _make_symbols(DEFAULT_TOP_N)
        weights, _ = equal_weight(fake_selected)
        capped = _apply_caps(weights, self.sector_map)
        for sym, w in capped.items():
            assert w <= MAX_POSITION_PCT + 1e-10, f"{sym} weight {w:.4f} exceeds max {MAX_POSITION_PCT}"

    def test_sector_cap_respected(self) -> None:
        """No sector exceeds MAX_SECTOR_PCT after capping."""
        fake_selected = _make_symbols(DEFAULT_TOP_N)
        weights, _ = equal_weight(fake_selected)
        capped = _apply_caps(weights, self.sector_map)

        sector_totals: dict[str, float] = {}
        for sym, w in capped.items():
            sec = self.sector_map.get(sym, "Unknown")
            sector_totals[sec] = sector_totals.get(sec, 0.0) + w

        for sec, total in sector_totals.items():
            assert total <= MAX_SECTOR_PCT + 1e-10, (
                f"Sector {sec} weight {total:.4f} exceeds max {MAX_SECTOR_PCT}"
            )

    def test_capped_weights_sum_to_one(self) -> None:
        """After position and sector caps, weights must re-normalize to ~1.0."""
        fake_selected = _make_symbols(DEFAULT_TOP_N)
        weights, _ = equal_weight(fake_selected)
        capped = _apply_caps(weights, self.sector_map)
        total = sum(capped.values())
        assert abs(total - 1.0) < 1e-6, f"Capped weights sum to {total}"

    def test_trade_plans_have_valid_fields(self) -> None:
        """Every TradePlan has non-empty symbol, valid side, positive shares."""
        fake_selected = _make_symbols(DEFAULT_TOP_N)
        weights, _ = equal_weight(fake_selected)
        capped = _apply_caps(weights, self.sector_map)
        regime = _determine_regime(self.prices, self.symbols[0], REBALANCE_DATE)
        plans = _generate_trade_plans(capped, regime)

        assert len(plans) > 0, "Expected at least one TradePlan"
        for plan in plans:
            assert plan.symbol, "TradePlan symbol must not be empty"
            assert isinstance(plan.side, Side)
            assert plan.target_shares > 0, f"{plan.symbol}: shares must be > 0"
            assert plan.order_type in ("TWAP", "VWAP", "MARKET")
            assert plan.reason, "TradePlan reason must not be empty"
            assert isinstance(plan.decision_timestamp, datetime)

    def test_trade_plan_weights_sum_to_approximately_one(self) -> None:
        """Implied weights from TradePlans must sum to ~1.0 (within regime scaling)."""
        fake_selected = _make_symbols(DEFAULT_TOP_N)
        weights, _ = equal_weight(fake_selected)
        capped = _apply_caps(weights, self.sector_map)
        regime = _determine_regime(self.prices, self.symbols[0], REBALANCE_DATE)
        plans = _generate_trade_plans(capped, regime, portfolio_value=1_000_000.0)

        exposure = BULL_EXPOSURE if regime == RegimeState.BULL else BEAR_EXPOSURE
        total_value = sum(p.target_shares * 50.0 for p in plans)
        implied_exposure = total_value / 1_000_000.0

        # Allow tolerance for integer rounding of share counts
        assert abs(implied_exposure - exposure) < 0.05, (
            f"Implied exposure {implied_exposure:.4f} != expected {exposure}"
        )

    def test_no_position_exceeds_ten_percent(self) -> None:
        """No single TradePlan implies > 10% of portfolio value."""
        fake_selected = _make_symbols(DEFAULT_TOP_N)
        weights, _ = equal_weight(fake_selected)
        capped = _apply_caps(weights, self.sector_map)
        regime = _determine_regime(self.prices, self.symbols[0], REBALANCE_DATE)
        plans = _generate_trade_plans(capped, regime, portfolio_value=1_000_000.0)

        for plan in plans:
            implied_pct = (plan.target_shares * 50.0) / 1_000_000.0
            assert implied_pct <= MAX_POSITION_PCT + 0.02, (
                f"{plan.symbol}: implied {implied_pct:.4f} > max {MAX_POSITION_PCT}"
            )

    def test_full_pipeline_end_to_end(self) -> None:
        """Orchestrate the entire pipeline and verify final output contracts."""
        # 1. Build features
        feat_df, factor_names = _build_feature_matrix(
            self.prices,
            self.symbols,
            REBALANCE_DATE,
        )

        # 2. Normalize
        normed = _normalize_features(feat_df, factor_names)

        # 3. Impute
        imputed, imp_diag = cross_sectional_impute(normed, max_missing_pct=0.30)
        assert not imp_diag.has_errors

        # 4. Combine with Ridge
        X = imputed[factor_names].dropna()
        rng = np.random.default_rng(7)
        y = pd.Series(rng.normal(0, 0.02, size=len(X)), index=X.index)
        model = RidgeModel(alpha=1.0)
        model.fit(X, y)
        scores, _ = model.predict(X)
        score_series = pd.Series(
            scores.values,
            index=imputed.loc[X.index, COL_SYMBOL].values,
        )

        # 5. Allocate top-20 with sell_buffer
        selected, _ = select_top_n(
            score_series,
            n=DEFAULT_TOP_N,
            sell_buffer=DEFAULT_SELL_BUFFER,
        )
        weights, _ = equal_weight(selected)

        # 6. Regime overlay
        regime = _determine_regime(self.prices, self.symbols[0], REBALANCE_DATE)

        # 7. Apply position and sector caps
        capped = _apply_caps(weights, self.sector_map)

        # 8. Generate TradePlans
        plans = _generate_trade_plans(capped, regime)

        # --- Assertions ---
        assert len(plans) > 0
        assert len(plans) <= DEFAULT_TOP_N

        total_weight = sum(capped.values())
        assert abs(total_weight - 1.0) < 1e-6

        for plan in plans:
            assert plan.symbol
            assert plan.target_shares > 0
            assert isinstance(plan.side, Side)

        exposure = BULL_EXPOSURE if regime == RegimeState.BULL else BEAR_EXPOSURE
        total_value = sum(p.target_shares * 50.0 for p in plans)
        implied = total_value / 1_000_000.0
        assert abs(implied - exposure) < 0.05

    def test_cost_model_returns_positive_bps(self) -> None:
        """Transaction cost estimate for a liquid stock is positive and reasonable."""
        cost_bps, diag = estimate_cost_bps(adv=50_000_000.0)
        assert not diag.has_errors
        assert cost_bps > 0.0
        assert cost_bps < 100.0  # sanity: <100 bps for liquid stock

    def test_portfolio_build_result_contract(self) -> None:
        """PortfolioBuildResult can be constructed with valid pipeline outputs."""
        fake_selected = _make_symbols(DEFAULT_TOP_N)
        weights, _ = equal_weight(fake_selected)
        capped = _apply_caps(weights, self.sector_map)
        regime = _determine_regime(self.prices, self.symbols[0], REBALANCE_DATE)
        plans = _generate_trade_plans(capped, regime)

        result = PortfolioBuildResult(
            trade_plans=plans,
            cost_estimate_usd=150.0,
            turnover_pct=0.25,
            regime_state=regime,
            rebalance_date=REBALANCE_DATE,
            held_positions=0,
            new_entries=len(plans),
            exits=0,
            skipped_reason=None,
        )
        assert result.skipped_reason is None
        assert result.new_entries == len(plans)
        assert len(result.trade_plans) > 0
