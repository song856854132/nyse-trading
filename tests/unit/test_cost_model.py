"""Unit tests for nyse_core.cost_model."""

from __future__ import annotations

import math

import pytest

from nyse_core.cost_model import estimate_cost_bps, should_trade
from nyse_core.schema import (
    BASE_SPREAD_BPS,
    DEFAULT_COMMISSION_PER_SHARE,
    EARNINGS_WEEK_MULTIPLIER,
    MONDAY_MULTIPLIER,
)

# ── estimate_cost_bps ────────────────────────────────────────────────────────


class TestEstimateCostBps:
    """Tests for the dynamic spread + commission cost model."""

    def test_baseline_50m_adv(self) -> None:
        """At ADV=50M the spread component equals BASE_SPREAD_BPS (sqrt(1)=1)."""
        cost, diag = estimate_cost_bps(adv=50_000_000)
        expected_spread = BASE_SPREAD_BPS / math.sqrt(50_000_000 / 50_000_000)
        commission = DEFAULT_COMMISSION_PER_SHARE * 2 / 50.0 * 10_000
        assert cost == pytest.approx(expected_spread + commission, rel=1e-6)
        assert not diag.has_errors

    def test_low_adv_higher_cost(self) -> None:
        """Illiquid stocks (low ADV) should have higher cost."""
        cost_low, _ = estimate_cost_bps(adv=5_000_000)
        cost_high, _ = estimate_cost_bps(adv=200_000_000)
        assert cost_low > cost_high

    def test_monday_multiplier_applied(self) -> None:
        """Monday trades should be 30% more expensive (spread component)."""
        cost_normal, _ = estimate_cost_bps(adv=50_000_000, is_monday=False)
        cost_monday, _ = estimate_cost_bps(adv=50_000_000, is_monday=True)
        # Commission is flat, so Monday cost > normal cost
        assert cost_monday > cost_normal
        # Verify the spread portion scales by MONDAY_MULTIPLIER
        commission = DEFAULT_COMMISSION_PER_SHARE * 2 / 50.0 * 10_000
        spread_normal = cost_normal - commission
        spread_monday = cost_monday - commission
        assert spread_monday == pytest.approx(spread_normal * MONDAY_MULTIPLIER, rel=1e-6)

    def test_earnings_week_multiplier_applied(self) -> None:
        """Earnings week trades should be 50% more expensive (spread component)."""
        cost_normal, _ = estimate_cost_bps(adv=50_000_000, is_earnings_week=False)
        cost_earn, _ = estimate_cost_bps(adv=50_000_000, is_earnings_week=True)
        commission = DEFAULT_COMMISSION_PER_SHARE * 2 / 50.0 * 10_000
        spread_normal = cost_normal - commission
        spread_earn = cost_earn - commission
        assert spread_earn == pytest.approx(spread_normal * EARNINGS_WEEK_MULTIPLIER, rel=1e-6)

    def test_both_multipliers_stack(self) -> None:
        """Monday + earnings should compound the multipliers."""
        cost_both, _ = estimate_cost_bps(adv=50_000_000, is_monday=True, is_earnings_week=True)
        commission = DEFAULT_COMMISSION_PER_SHARE * 2 / 50.0 * 10_000
        expected_spread = BASE_SPREAD_BPS * MONDAY_MULTIPLIER * EARNINGS_WEEK_MULTIPLIER
        assert cost_both == pytest.approx(expected_spread + commission, rel=1e-6)

    def test_zero_adv_returns_error(self) -> None:
        """ADV=0 should produce error diagnostic and cost=0."""
        cost, diag = estimate_cost_bps(adv=0)
        assert cost == 10_000.0
        assert diag.has_errors

    def test_negative_adv_returns_error(self) -> None:
        """Negative ADV should produce error diagnostic."""
        cost, diag = estimate_cost_bps(adv=-1_000_000)
        assert cost == 10_000.0
        assert diag.has_errors


# ── should_trade ─────────────────────────────────────────────────────────────


class TestShouldTrade:
    """Tests for Carver's position inertia decision."""

    def test_large_delta_triggers_trade(self) -> None:
        """Weight change exceeding threshold should trigger a trade."""
        trade, diag = should_trade(
            current_weight=0.0, target_weight=0.05, cost_bps=10.0, inertia_threshold=0.01
        )
        assert trade is True
        assert not diag.has_errors

    def test_small_delta_suppressed(self) -> None:
        """Weight change within threshold should be suppressed."""
        trade, diag = should_trade(
            current_weight=0.05, target_weight=0.052, cost_bps=10.0, inertia_threshold=0.01
        )
        assert trade is False

    def test_exact_threshold_not_traded(self) -> None:
        """Delta exactly equal to threshold should NOT trade (strict >)."""
        trade, _ = should_trade(
            current_weight=0.05, target_weight=0.06, cost_bps=10.0, inertia_threshold=0.01
        )
        assert trade is False

    def test_zero_to_nonzero_trades(self) -> None:
        """New entry (0 -> target) should always trade if delta > threshold."""
        trade, _ = should_trade(current_weight=0.0, target_weight=0.05, cost_bps=10.0, inertia_threshold=0.01)
        assert trade is True

    def test_diagnostics_contain_reasoning(self) -> None:
        """Diagnostics should explain the decision."""
        _, diag = should_trade(current_weight=0.0, target_weight=0.05, cost_bps=10.0, inertia_threshold=0.01)
        assert len(diag.messages) > 0
        msg = diag.messages[0].message
        assert "trade" in msg.lower()
