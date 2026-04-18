"""Unit tests for nyse_core.risk."""

from __future__ import annotations

import pytest

from nyse_core.risk import (
    apply_position_caps,
    apply_regime_overlay,
    apply_sector_caps,
    check_beta_cap,
    check_daily_loss,
    check_earnings_exposure,
)
from nyse_core.schema import (
    BEAR_EXPOSURE,
    BETA_CAP_HIGH,
    BETA_CAP_LOW,
    BULL_EXPOSURE,
    DAILY_LOSS_LIMIT,
    MAX_POSITION_PCT,
    MAX_SECTOR_PCT,
    RegimeState,
)

# ── apply_regime_overlay ─────────────────────────────────────────────────────


class TestRegimeOverlay:
    """Tests for SMA200-based regime detection."""

    def test_bull_regime(self) -> None:
        """SPY above SMA200 -> BULL, exposure unchanged."""
        scaled, regime, diag = apply_regime_overlay(1.0, spy_price=450, spy_sma200=420)
        assert regime == RegimeState.BULL
        assert scaled == pytest.approx(1.0 * BULL_EXPOSURE)
        assert not diag.has_errors

    def test_bear_regime(self) -> None:
        """SPY below SMA200 -> BEAR, exposure scaled to 40%."""
        scaled, regime, diag = apply_regime_overlay(1.0, spy_price=400, spy_sma200=420)
        assert regime == RegimeState.BEAR
        assert scaled == pytest.approx(1.0 * BEAR_EXPOSURE)

    def test_equal_price_is_bear(self) -> None:
        """SPY == SMA200 -> BEAR (not strictly above)."""
        _, regime, _ = apply_regime_overlay(1.0, spy_price=420, spy_sma200=420)
        assert regime == RegimeState.BEAR

    def test_exposure_scales_correctly(self) -> None:
        """Bear with 0.8 exposure -> 0.8 * 0.4 = 0.32."""
        scaled, _, _ = apply_regime_overlay(0.8, spy_price=400, spy_sma200=420)
        assert scaled == pytest.approx(0.8 * BEAR_EXPOSURE)


# ── apply_position_caps ──────────────────────────────────────────────────────


class TestPositionCaps:
    """Tests for individual position capping."""

    def test_no_cap_needed(self) -> None:
        """Equal weights below cap should pass through unchanged."""
        weights = {"A": 0.05, "B": 0.05, "C": 0.05}
        capped, diag = apply_position_caps(weights, max_pct=0.10)
        assert capped == pytest.approx(weights)

    def test_cap_enforced(self) -> None:
        """A position above max_pct should be capped."""
        weights = {"A": 0.20, "B": 0.40, "C": 0.40}
        capped, _ = apply_position_caps(weights, max_pct=MAX_POSITION_PCT)
        assert capped["B"] <= MAX_POSITION_PCT + 1e-9
        assert capped["C"] <= MAX_POSITION_PCT + 1e-9

    def test_total_preserved(self) -> None:
        """Total weight should be approximately preserved after capping.

        Uses enough positions so the cap-respecting total can equal the original.
        With 10 positions and 20% cap, max achievable = 200% >> 100% original.
        """
        weights = {
            "A": 0.05,
            "B": 0.05,
            "C": 0.05,
            "D": 0.05,
            "E": 0.05,
            "F": 0.05,
            "G": 0.05,
            "H": 0.25,
            "I": 0.20,
            "J": 0.20,
        }
        capped, _ = apply_position_caps(weights, max_pct=0.20)
        assert sum(capped.values()) == pytest.approx(sum(weights.values()), rel=1e-4)

    def test_empty_weights(self) -> None:
        """Empty dict should return empty dict."""
        capped, _ = apply_position_caps({})
        assert capped == {}


# ── apply_sector_caps ────────────────────────────────────────────────────────


class TestSectorCaps:
    """Tests for sector-level capping."""

    def test_no_cap_needed(self) -> None:
        """Diversified sectors below cap pass through."""
        weights = {"A": 0.10, "B": 0.10, "C": 0.10}
        sectors = {"A": "Tech", "B": "Health", "C": "Finance"}
        capped, _ = apply_sector_caps(weights, sectors, max_sector_pct=0.30)
        assert capped == pytest.approx(weights)

    def test_sector_cap_enforced(self) -> None:
        """A sector above max_sector_pct should be reduced."""
        weights = {
            "A": 0.15,
            "B": 0.15,
            "C": 0.15,
            "D": 0.10,
            "E": 0.10,
            "F": 0.10,
            "G": 0.10,
            "H": 0.10,
            "I": 0.05,
        }
        sectors = {
            "A": "Tech",
            "B": "Tech",
            "C": "Tech",  # Tech = 0.45 > 0.30
            "D": "Health",
            "E": "Health",
            "F": "Finance",
            "G": "Energy",
            "H": "Consumer",
            "I": "Utilities",
        }
        capped, _ = apply_sector_caps(weights, sectors, max_sector_pct=MAX_SECTOR_PCT)
        tech_total = sum(capped[s] for s in ["A", "B", "C"])
        assert tech_total <= MAX_SECTOR_PCT + 1e-6

    def test_total_preserved(self) -> None:
        """Total weight should be approximately preserved.

        Uses enough sectors so the excess has room to redistribute without
        cascading cap breaches.
        """
        weights = {
            "A": 0.20,
            "B": 0.25,
            "C": 0.15,
            "D": 0.10,
            "E": 0.10,
            "F": 0.10,
            "G": 0.10,
        }
        sectors = {
            "A": "Tech",
            "B": "Tech",  # Tech = 0.45 > 0.30
            "C": "Health",
            "D": "Health",  # Health = 0.25
            "E": "Finance",  # Finance = 0.10
            "F": "Energy",  # Energy = 0.10
            "G": "Consumer",  # Consumer = 0.10
        }
        capped, _ = apply_sector_caps(weights, sectors, max_sector_pct=0.30)
        assert sum(capped.values()) == pytest.approx(1.0, rel=1e-4)

    def test_empty_weights(self) -> None:
        """Empty dict should return empty dict."""
        capped, _ = apply_sector_caps({}, {})
        assert capped == {}


# ── check_beta_cap ───────────────────────────────────────────────────────────


class TestBetaCap:
    """Tests for portfolio beta range check."""

    def test_within_range(self) -> None:
        """Beta=1.0 should be within [0.5, 1.5]."""
        within, diag = check_beta_cap(1.0)
        assert within is True
        assert not diag.has_warnings

    def test_below_range(self) -> None:
        """Beta=0.3 should fail."""
        within, diag = check_beta_cap(0.3)
        assert within is False
        assert diag.has_warnings

    def test_above_range(self) -> None:
        """Beta=2.0 should fail."""
        within, diag = check_beta_cap(2.0)
        assert within is False

    def test_at_boundaries(self) -> None:
        """Beta at exactly the boundaries should pass."""
        assert check_beta_cap(BETA_CAP_LOW)[0] is True
        assert check_beta_cap(BETA_CAP_HIGH)[0] is True


# ── check_daily_loss ─────────────────────────────────────────────────────────


class TestDailyLoss:
    """Tests for daily loss halt trigger."""

    def test_no_halt_on_positive(self) -> None:
        """Positive return should not halt."""
        halt, _ = check_daily_loss(0.01)
        assert halt is False

    def test_halt_on_large_loss(self) -> None:
        """Return below limit should trigger halt."""
        halt, diag = check_daily_loss(-0.05)
        assert halt is True
        assert diag.has_warnings

    def test_exact_limit_triggers_halt(self) -> None:
        """Return exactly at limit should trigger halt (<=)."""
        halt, _ = check_daily_loss(DAILY_LOSS_LIMIT)
        assert halt is True

    def test_just_above_limit_no_halt(self) -> None:
        """Return slightly above limit should NOT halt."""
        halt, _ = check_daily_loss(DAILY_LOSS_LIMIT + 0.001)
        assert halt is False


# ── check_earnings_exposure ──────────────────────────────────────────────────


class TestEarningsExposure:
    """Tests for earnings proximity capping."""

    def test_no_earnings(self) -> None:
        """No stocks near earnings -> weights unchanged."""
        weights = {"A": 0.10, "B": 0.10}
        result, _ = check_earnings_exposure(weights, {})
        assert result == pytest.approx(weights)

    def test_cap_applied(self) -> None:
        """Stock reporting in 1 day should be capped at 5%."""
        weights = {"A": 0.10, "B": 0.10}
        reporting = {"A": 1}
        result, diag = check_earnings_exposure(weights, reporting, cap=0.05, days=2)
        assert result["A"] == pytest.approx(0.05)
        assert len(diag.messages) > 0

    def test_excess_redistributed(self) -> None:
        """Excess from capped stock should go to safe stocks."""
        weights = {"A": 0.10, "B": 0.10, "C": 0.10}
        reporting = {"A": 1}
        result, _ = check_earnings_exposure(weights, reporting, cap=0.05, days=2)
        # A capped at 0.05, excess 0.05 distributed to B and C equally
        assert result["A"] == pytest.approx(0.05)
        total = sum(result.values())
        assert total == pytest.approx(0.30, rel=1e-6)

    def test_stock_beyond_window_not_capped(self) -> None:
        """Stock reporting in 5 days (> window 2) should not be capped."""
        weights = {"A": 0.10}
        reporting = {"A": 5}
        result, _ = check_earnings_exposure(weights, reporting, cap=0.05, days=2)
        assert result["A"] == pytest.approx(0.10)

    def test_empty_weights(self) -> None:
        """Empty weights should return empty dict."""
        result, _ = check_earnings_exposure({}, {"A": 1})
        assert result == {}
