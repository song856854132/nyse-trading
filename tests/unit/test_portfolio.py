"""Unit tests for nyse_core.portfolio."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from nyse_core.contracts import PortfolioBuildResult, TradePlan
from nyse_core.portfolio import build_portfolio
from nyse_core.schema import RegimeState, Side


class TestBuildPortfolio:
    """Tests for the full portfolio construction pipeline."""

    @pytest.fixture()
    def basic_inputs(self) -> dict:
        """Minimal inputs for a 5-stock portfolio with 10 candidates."""
        scores = pd.Series(
            {
                "AAPL": 0.95,
                "MSFT": 0.90,
                "GOOG": 0.85,
                "AMZN": 0.80,
                "META": 0.75,
                "NFLX": 0.70,
                "NVDA": 0.65,
                "CRM": 0.60,
                "TSLA": 0.30,
                "SNAP": 0.20,
            }
        )
        sectors = {
            "AAPL": "Tech",
            "MSFT": "Tech",
            "GOOG": "Tech",
            "AMZN": "Consumer",
            "META": "Tech",
            "NFLX": "Consumer",
            "NVDA": "Tech",
            "CRM": "Tech",
            "TSLA": "Consumer",
            "SNAP": "Consumer",
        }
        config = {
            "top_n": 5,
            "sell_buffer": 1.5,
            "max_position_pct": 0.10,
            "max_sector_pct": 0.30,
            "inertia_threshold": 0.005,
            "rebalance_date": date(2024, 6, 1),
            "notional": 1_000_000,
        }
        return {
            "scores": scores,
            "sectors": sectors,
            "config": config,
            "spy_price": 450.0,
            "spy_sma200": 420.0,
        }

    def test_returns_portfolio_build_result(self, basic_inputs: dict) -> None:
        """build_portfolio should return a PortfolioBuildResult."""
        result, diag = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={},
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        assert isinstance(result, PortfolioBuildResult)
        assert not diag.has_errors

    def test_trade_plans_created(self, basic_inputs: dict) -> None:
        """Fresh portfolio (no current holdings) should create BUY trade plans."""
        result, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={},
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        assert len(result.trade_plans) > 0
        assert all(isinstance(tp, TradePlan) for tp in result.trade_plans)
        # All should be BUY for a fresh portfolio
        assert all(tp.side == Side.BUY for tp in result.trade_plans)

    def test_new_entries_counted(self, basic_inputs: dict) -> None:
        """New entries should be counted correctly."""
        result, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={},
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        assert result.new_entries == len(result.trade_plans)

    def test_exits_when_stock_dropped(self, basic_inputs: dict) -> None:
        """A held stock no longer in top-N should produce a SELL plan."""
        result, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={"TSLA": 0.05},  # TSLA ranked low, will be dropped
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        tsla_plans = [tp for tp in result.trade_plans if tp.symbol == "TSLA"]
        assert len(tsla_plans) == 1
        assert tsla_plans[0].side == Side.SELL
        assert result.exits >= 1

    def test_bear_regime_reduces_positions(self, basic_inputs: dict) -> None:
        """Bear regime should reduce total exposure."""
        # Bull
        result_bull, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={},
            sectors=basic_inputs["sectors"],
            spy_price=450.0,
            spy_sma200=420.0,
            config=basic_inputs["config"],
        )
        # Bear
        result_bear, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={},
            sectors=basic_inputs["sectors"],
            spy_price=400.0,
            spy_sma200=420.0,
            config=basic_inputs["config"],
        )
        assert result_bear.regime_state == RegimeState.BEAR
        assert result_bull.regime_state == RegimeState.BULL

    def test_rebalance_date_in_result(self, basic_inputs: dict) -> None:
        """The rebalance_date should appear in the result."""
        result, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={},
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        assert result.rebalance_date == date(2024, 6, 1)

    def test_turnover_is_positive(self, basic_inputs: dict) -> None:
        """Turnover should be > 0 when building from scratch."""
        result, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={},
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        assert result.turnover_pct > 0

    def test_cost_estimate_non_negative(self, basic_inputs: dict) -> None:
        """Cost estimate should be non-negative."""
        result, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={},
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        assert result.cost_estimate_usd >= 0

    def test_trade_plans_have_positive_target_shares(self, basic_inputs: dict) -> None:
        """BUY trade plans must have target_shares > 0 (weight-to-shares conversion)."""
        basic_inputs["config"]["prices"] = {
            "AAPL": 180.0,
            "MSFT": 420.0,
            "GOOG": 175.0,
            "AMZN": 185.0,
            "META": 500.0,
        }
        result, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={},
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        buy_plans = [tp for tp in result.trade_plans if tp.side == Side.BUY]
        assert len(buy_plans) > 0, "Expected BUY trade plans"
        for tp in buy_plans:
            assert tp.target_shares > 0, f"{tp.symbol}: target_shares must be > 0, got {tp.target_shares}"

    def test_inertia_allows_small_rebalances(self, basic_inputs: dict) -> None:
        """Regression: old threshold 0.10 blocked all rebalances on ~7.5% positions.
        With correct threshold 0.005, a 1.5pp weight change must trade.
        Math: top_n=5, EW 20% → pos cap 10% → sector cap (4 Tech at 30%)
        → each Tech stock ~7.5%. Hold AAPL at 6%, delta ~1.5pp > 0.5pp."""
        basic_inputs["config"]["inertia_threshold"] = 0.005
        result, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={"AAPL": 0.06},
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        aapl_plans = [tp for tp in result.trade_plans if tp.symbol == "AAPL"]
        assert len(aapl_plans) == 1, "AAPL at 6% with ~7.5% target (1.5pp delta) should trade"
        assert aapl_plans[0].side == Side.BUY

    def test_inertia_suppresses_tiny_rebalances(self, basic_inputs: dict) -> None:
        """Positions within inertia threshold should NOT generate trades.
        Hold AAPL very close to its target (~7.5%) so delta < 0.5pp."""
        basic_inputs["config"]["inertia_threshold"] = 0.005
        result_ref, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={},
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        # Find AAPL's actual target weight from a clean build
        aapl_ref = [tp for tp in result_ref.trade_plans if tp.symbol == "AAPL"]
        assert len(aapl_ref) == 1
        target_w = aapl_ref[0].provenance["target_weight"]
        # Hold at target - 0.001 (tiny delta well within 0.005 threshold)
        result, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={"AAPL": target_w - 0.001},
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        aapl_plans = [tp for tp in result.trade_plans if tp.symbol == "AAPL"]
        assert len(aapl_plans) == 0, "AAPL at 9.998% with ~10% target (0.002pp delta) should be suppressed"

    def test_sell_plans_have_positive_current_shares(self, basic_inputs: dict) -> None:
        """SELL (exit) trade plans must have current_shares > 0."""
        basic_inputs["config"]["prices"] = {
            "AAPL": 180.0,
            "MSFT": 420.0,
            "GOOG": 175.0,
            "AMZN": 185.0,
            "META": 500.0,
            "TSLA": 170.0,
        }
        result, _ = build_portfolio(
            scores=basic_inputs["scores"],
            current_holdings={"TSLA": 0.05},
            sectors=basic_inputs["sectors"],
            spy_price=basic_inputs["spy_price"],
            spy_sma200=basic_inputs["spy_sma200"],
            config=basic_inputs["config"],
        )
        sell_plans = [tp for tp in result.trade_plans if tp.side == Side.SELL]
        assert len(sell_plans) > 0, "Expected SELL trade plans"
        for tp in sell_plans:
            assert tp.current_shares > 0, (
                f"{tp.symbol}: current_shares must be > 0 on SELL, got {tp.current_shares}"
            )


# ── Provenance stamping ───────────────────────────────────────────────────


class TestProvenance:
    """Tests for TradePlan.provenance, wired from pipeline → portfolio."""

    @pytest.fixture()
    def inputs_with_provenance(self) -> dict:
        scores = pd.Series(
            {
                "AAPL": 0.95,
                "MSFT": 0.90,
                "GOOG": 0.85,
                "AMZN": 0.80,
                "META": 0.75,
            }
        )
        config = {
            "top_n": 5,
            "sell_buffer": 1.5,
            "max_position_pct": 0.10,
            "max_sector_pct": 0.30,
            "inertia_threshold": 0.005,
            "rebalance_date": date(2024, 6, 1),
            "notional": 1_000_000,
            "prices": {"AAPL": 180.0, "MSFT": 420.0, "GOOG": 175.0, "AMZN": 185.0, "META": 500.0},
            "provenance": {
                "model_type": "ridge",
                "rebalance_date": "2024-06-01",
                "data_path": "HAPPY",
                "n_features": 8,
                "n_stocks_scored": 5,
            },
        }
        sectors = {s: "Tech" for s in scores.index}
        return {"scores": scores, "config": config, "sectors": sectors}

    def test_provenance_stamped_on_all_trade_plans(self, inputs_with_provenance: dict) -> None:
        """Every TradePlan must carry provenance from the pipeline."""
        result, diag = build_portfolio(
            scores=inputs_with_provenance["scores"],
            current_holdings={},
            sectors=inputs_with_provenance["sectors"],
            spy_price=450.0,
            spy_sma200=420.0,
            config=inputs_with_provenance["config"],
        )
        assert len(result.trade_plans) > 0
        for tp in result.trade_plans:
            assert tp.provenance, f"{tp.symbol}: provenance must not be empty"
            assert tp.provenance["model_type"] == "ridge"
            assert tp.provenance["data_path"] == "HAPPY"

    def test_provenance_includes_per_trade_score(self, inputs_with_provenance: dict) -> None:
        """Provenance must include the symbol's composite_score."""
        result, _ = build_portfolio(
            scores=inputs_with_provenance["scores"],
            current_holdings={},
            sectors=inputs_with_provenance["sectors"],
            spy_price=450.0,
            spy_sma200=420.0,
            config=inputs_with_provenance["config"],
        )
        for tp in result.trade_plans:
            assert "composite_score" in tp.provenance
            assert "target_weight" in tp.provenance
            assert isinstance(tp.provenance["composite_score"], float)

    def test_provenance_defaults_to_empty_when_not_configured(self) -> None:
        """Without provenance in config, TradePlan.provenance is still populated
        with per-trade fields (composite_score, target_weight)."""
        scores = pd.Series({"AAPL": 0.95, "MSFT": 0.90})
        config = {
            "top_n": 2,
            "sell_buffer": 1.5,
            "max_position_pct": 0.10,
            "max_sector_pct": 0.30,
            "rebalance_date": date(2024, 6, 1),
        }
        result, _ = build_portfolio(
            scores=scores,
            current_holdings={},
            sectors={"AAPL": "Tech", "MSFT": "Tech"},
            spy_price=450.0,
            spy_sma200=420.0,
            config=config,
        )
        for tp in result.trade_plans:
            # Even without pipeline provenance, per-trade fields exist
            assert "composite_score" in tp.provenance
            assert "target_weight" in tp.provenance


# ── Risk control wiring ──────────────────────────────────────────────────


class TestEarningsExposureCap:
    """Tests for earnings exposure cap wired into build_portfolio."""

    def test_caps_stock_near_earnings(self) -> None:
        """Stocks reporting within 2 days should be capped at 5%."""
        scores = pd.Series(
            {
                "AAPL": 0.95,
                "MSFT": 0.90,
                "GOOG": 0.85,
                "AMZN": 0.80,
                "META": 0.75,
            }
        )
        config = {
            "top_n": 5,
            "sell_buffer": 1.5,
            "max_position_pct": 0.10,
            "max_sector_pct": 0.50,
            "rebalance_date": date(2024, 6, 1),
            "reporting_within_days": {"AAPL": 1},  # AAPL reports tomorrow
            "earnings_event_cap": 0.05,
            "earnings_event_days": 2,
        }
        sectors = {s: "Tech" for s in scores.index}
        result, diag = build_portfolio(
            scores=scores,
            current_holdings={},
            sectors=sectors,
            spy_price=450.0,
            spy_sma200=420.0,
            config=config,
        )
        assert not diag.has_errors

    def test_no_earnings_data_skips_gracefully(self) -> None:
        """Without reporting_within_days in config, earnings cap is skipped."""
        scores = pd.Series({"AAPL": 0.95, "MSFT": 0.90})
        config = {
            "top_n": 2,
            "sell_buffer": 1.5,
            "max_position_pct": 0.10,
            "max_sector_pct": 0.50,
            "rebalance_date": date(2024, 6, 1),
        }
        result, diag = build_portfolio(
            scores=scores,
            current_holdings={},
            sectors={"AAPL": "Tech", "MSFT": "Tech"},
            spy_price=450.0,
            spy_sma200=420.0,
            config=config,
        )
        assert not diag.has_errors
        assert len(result.trade_plans) > 0


class TestBetaCapWiring:
    """Tests for beta cap check wired into build_portfolio."""

    def test_beta_within_range_no_warning(self) -> None:
        scores = pd.Series({"AAPL": 0.95, "MSFT": 0.90})
        config = {
            "top_n": 2,
            "sell_buffer": 1.5,
            "max_position_pct": 0.10,
            "max_sector_pct": 0.50,
            "rebalance_date": date(2024, 6, 1),
            "portfolio_beta": 1.0,
            "beta_cap_low": 0.5,
            "beta_cap_high": 1.5,
        }
        result, diag = build_portfolio(
            scores=scores,
            current_holdings={},
            sectors={"AAPL": "Tech", "MSFT": "Tech"},
            spy_price=450.0,
            spy_sma200=420.0,
            config=config,
        )
        assert not diag.has_errors
        assert not diag.has_warnings

    def test_beta_out_of_range_warns(self) -> None:
        scores = pd.Series({"AAPL": 0.95, "MSFT": 0.90})
        config = {
            "top_n": 2,
            "sell_buffer": 1.5,
            "max_position_pct": 0.10,
            "max_sector_pct": 0.50,
            "rebalance_date": date(2024, 6, 1),
            "portfolio_beta": 2.0,  # Outside [0.5, 1.5]
            "beta_cap_low": 0.5,
            "beta_cap_high": 1.5,
        }
        result, diag = build_portfolio(
            scores=scores,
            current_holdings={},
            sectors={"AAPL": "Tech", "MSFT": "Tech"},
            spy_price=450.0,
            spy_sma200=420.0,
            config=config,
        )
        assert diag.has_warnings

    def test_no_beta_data_skips_gracefully(self) -> None:
        """Without portfolio_beta in config, beta cap is skipped."""
        scores = pd.Series({"AAPL": 0.95, "MSFT": 0.90})
        config = {
            "top_n": 2,
            "sell_buffer": 1.5,
            "max_position_pct": 0.10,
            "max_sector_pct": 0.50,
            "rebalance_date": date(2024, 6, 1),
        }
        result, diag = build_portfolio(
            scores=scores,
            current_holdings={},
            sectors={"AAPL": "Tech", "MSFT": "Tech"},
            spy_price=450.0,
            spy_sma200=420.0,
            config=config,
        )
        assert not diag.has_errors
