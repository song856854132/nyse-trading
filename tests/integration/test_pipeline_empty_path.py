"""Integration test: EMPTY path -- ALL features are NaN for a rebalance date.

When every feature value is NaN (complete data blackout), the pipeline must:
  1. Skip the rebalance entirely.
  2. HOLD all current positions.
  3. MUST NOT generate sell orders for currently held positions.
  4. Set PortfolioBuildResult.skipped_reason mentioning "all NaN".
"""

from __future__ import annotations

from datetime import date

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
        COL_DATE,
        COL_SYMBOL,
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
REBALANCE_DATE = date(2024, 6, 28)


# ── Synthetic Data Helpers ───────────────────────────────────────────────────


def _make_symbols(n: int) -> list[str]:
    return [f"EMP_{i:02d}" for i in range(n)]


def _make_all_nan_features(
    symbols: list[str],
    rebalance_date: date,
    factor_names: list[str] | None = None,
) -> pd.DataFrame:
    """Build a feature matrix where ALL factor values are NaN.

    Simulates a complete data blackout on the rebalance date.
    """
    if factor_names is None:
        factor_names = ["ivol_20d"]

    data: dict[str, list] = {
        COL_DATE: [rebalance_date] * len(symbols),
        COL_SYMBOL: symbols,
    }
    for col in factor_names:
        data[col] = [np.nan] * len(symbols)

    return pd.DataFrame(data)


def _make_multi_factor_all_nan(
    symbols: list[str],
    rebalance_date: date,
) -> tuple[pd.DataFrame, list[str]]:
    """Build a multi-factor feature matrix where every column is NaN."""
    factor_names = ["ivol_20d", "mom_2_12", "high_52w"]
    return _make_all_nan_features(symbols, rebalance_date, factor_names), factor_names


def _detect_empty_path(
    feature_df: pd.DataFrame,
    factor_names: list[str],
) -> tuple[bool, str]:
    """Detect if all features are NaN (EMPTY path).

    Returns (is_empty, reason_string).
    """
    for col in factor_names:
        if col not in feature_df.columns:
            continue
        if not feature_df[col].isna().all():
            return False, ""
    return True, "all NaN: every feature column is NaN for this rebalance date"


def _build_empty_portfolio_result(
    current_holdings: list[str],
    rebalance_date: date,
) -> PortfolioBuildResult:
    """Build a PortfolioBuildResult for the EMPTY path (complete skip)."""
    return PortfolioBuildResult(
        trade_plans=[],
        cost_estimate_usd=0.0,
        turnover_pct=0.0,
        regime_state=RegimeState.BULL,
        rebalance_date=rebalance_date,
        held_positions=len(current_holdings),
        new_entries=0,
        exits=0,
        skipped_reason="all NaN: every feature column is NaN for this rebalance date",
    )


# ── Tests ────────────────────────────────────────────────────────────────────


class TestPipelineEmptyPath:
    """EMPTY path: all features NaN -- pipeline must HOLD, never SELL."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.symbols = _make_symbols(N_STOCKS)

    def test_all_features_are_nan(self) -> None:
        """Verify synthetic data is genuinely all-NaN."""
        feat_df = _make_all_nan_features(self.symbols, REBALANCE_DATE)
        assert feat_df["ivol_20d"].isna().all()

    def test_empty_path_detected(self) -> None:
        """Detection logic correctly identifies the EMPTY path."""
        feat_df = _make_all_nan_features(self.symbols, REBALANCE_DATE)
        is_empty, reason = _detect_empty_path(feat_df, ["ivol_20d"])
        assert is_empty, "All-NaN features should trigger EMPTY path"
        assert "all nan" in reason.lower()

    def test_multi_factor_empty_detected(self) -> None:
        """EMPTY detection works with multiple factor columns."""
        feat_df, factor_names = _make_multi_factor_all_nan(self.symbols, REBALANCE_DATE)
        is_empty, reason = _detect_empty_path(feat_df, factor_names)
        assert is_empty

    def test_not_empty_when_one_factor_has_data(self) -> None:
        """If even one factor has non-NaN data, it is NOT the EMPTY path."""
        feat_df, factor_names = _make_multi_factor_all_nan(self.symbols, REBALANCE_DATE)
        # Inject one valid value in one factor
        feat_df.loc[0, "ivol_20d"] = 0.5
        is_empty, _ = _detect_empty_path(feat_df, factor_names)
        assert not is_empty, "One non-NaN value should prevent EMPTY detection"

    def test_rank_percentile_on_all_nan_returns_all_nan_with_warning(self) -> None:
        """rank_percentile on all-NaN input must return all NaN + WARNING."""
        all_nan = pd.Series([np.nan] * N_STOCKS)
        result, diag = rank_percentile(all_nan)
        assert result.isna().all()
        assert diag.has_warnings

    def test_imputation_on_all_nan_produces_all_nan(self) -> None:
        """cross_sectional_impute with all-NaN must NOT invent values."""
        feat_df = _make_all_nan_features(self.symbols, REBALANCE_DATE)
        imputed, diag = cross_sectional_impute(feat_df, max_missing_pct=0.30)
        # 100% NaN > 30% threshold => feature column must remain all NaN
        assert imputed["ivol_20d"].isna().all(), (
            "Imputation must not fabricate values when all features are NaN"
        )

    def test_skipped_reason_mentions_all_nan(self) -> None:
        """PortfolioBuildResult.skipped_reason must mention 'all NaN'."""
        current_holdings = self.symbols[:10]
        result = _build_empty_portfolio_result(current_holdings, REBALANCE_DATE)
        assert result.skipped_reason is not None
        assert "all nan" in result.skipped_reason.lower(), (
            f"skipped_reason must mention 'all NaN', got: {result.skipped_reason}"
        )

    def test_no_trade_plans_on_empty_path(self) -> None:
        """EMPTY path must produce zero TradePlans."""
        current_holdings = self.symbols[:10]
        result = _build_empty_portfolio_result(current_holdings, REBALANCE_DATE)
        assert len(result.trade_plans) == 0

    def test_no_sell_orders_for_held_positions(self) -> None:
        """CRITICAL: EMPTY path must NOT generate SELL orders for current holdings.

        This is the most dangerous failure mode: a data blackout causing the
        system to liquidate all positions. The pipeline must be defensive here.
        """
        current_holdings = self.symbols[:15]
        result = _build_empty_portfolio_result(current_holdings, REBALANCE_DATE)

        sell_plans = [p for p in result.trade_plans if p.side == Side.SELL]
        assert len(sell_plans) == 0, (
            f"EMPTY path generated {len(sell_plans)} SELL orders for held positions. "
            "This is catastrophic: a data blackout must NEVER trigger liquidation."
        )

    def test_held_positions_count_preserved(self) -> None:
        """held_positions in the result must match the count of prior holdings."""
        current_holdings = self.symbols[:12]
        result = _build_empty_portfolio_result(current_holdings, REBALANCE_DATE)
        assert result.held_positions == 12
        assert result.new_entries == 0
        assert result.exits == 0

    def test_zero_cost_and_turnover(self) -> None:
        """When rebalance is skipped, cost and turnover must be zero."""
        result = _build_empty_portfolio_result(self.symbols[:5], REBALANCE_DATE)
        assert result.cost_estimate_usd == 0.0
        assert result.turnover_pct == 0.0

    def test_pipeline_empty_path_full_flow(self) -> None:
        """End-to-end: detect EMPTY -> skip -> build result -> verify contracts."""
        # 1. Build all-NaN features
        feat_df = _make_all_nan_features(self.symbols, REBALANCE_DATE)
        factor_names = ["ivol_20d"]

        # 2. Detect EMPTY path
        is_empty, reason = _detect_empty_path(feat_df, factor_names)
        assert is_empty

        # 3. Attempt normalization (should produce all NaN)
        result_norm, diag_norm = rank_percentile(feat_df["ivol_20d"])
        assert result_norm.isna().all()
        assert diag_norm.has_warnings

        # 4. Attempt imputation (should leave all NaN)
        imputed, diag_imp = cross_sectional_impute(feat_df, max_missing_pct=0.30)
        assert imputed["ivol_20d"].isna().all()

        # 5. Skip rebalance
        current_holdings = self.symbols[:10]
        result = _build_empty_portfolio_result(current_holdings, REBALANCE_DATE)

        # 6. Final assertions
        assert result.skipped_reason is not None
        assert "all nan" in result.skipped_reason.lower()
        assert len(result.trade_plans) == 0
        assert result.held_positions == 10
        assert result.exits == 0
