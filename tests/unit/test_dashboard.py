"""Unit tests for the Streamlit dashboard module.

Tests rendering functions and DashboardState construction WITHOUT
launching Streamlit. Uses unittest.mock to patch st.* calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from nyse_ats.monitoring.dashboard import (
    IC_THRESHOLDS,
    MODE_COLORS,
    DashboardState,
    _generate_demo_state,
    compute_drawdown_series,
    compute_max_drawdown,
    ic_to_health,
    render_alerts,
    render_attribution,
    render_charts,
    render_factor_health,
    render_falsification_panel,
    render_header,
    render_last_rebalance,
    render_portfolio_section,
    render_risk_metrics,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> DashboardState:
    """Build a DashboardState with sensible defaults, overridable."""
    np.random.seed(0)
    dates = pd.bdate_range(end="2026-04-16", periods=60)
    defaults = dict(
        mode="PAPER",
        positions={"AAPL": 0.05, "MSFT": 0.05},
        cash_usd=50_000.0,
        unrealized_pnl=1_200.0,
        daily_returns=pd.Series(np.random.normal(0.0003, 0.01, 60), index=dates),
        regime_state="BULL",
        exposure=1.0,
        factor_health={"IVOL": "G", "Momentum": "Y", "ShortInt": "R"},
        factor_ic={"IVOL": 0.04, "Momentum": 0.02, "ShortInt": 0.01},
        attribution={"IVOL": 0.012, "Momentum": -0.003, "ShortInt": -0.001},
        last_rebalance_date="2026-04-11",
        last_rebalance_trades=5,
        last_rebalance_cost_usd=127.0,
        fill_rate=1.0,
        slippage_bps=4.2,
        alerts=[
            {"level": "W", "date": "2026-04-13", "message": "ShortInt IC dropped"},
            {"level": "I", "date": "2026-04-11", "message": "Rebalance done"},
        ],
        falsification_results=[
            {"trigger_id": "F1", "passed": True, "severity": "VETO", "value": 0.05, "threshold": 0.01},
            {"trigger_id": "F3", "passed": False, "severity": "VETO", "value": -0.30, "threshold": -0.25},
            {"trigger_id": "F4", "passed": True, "severity": "WARNING", "value": 0.08, "threshold": 0.15},
        ],
        cost_drag_annual=1.8,
        annual_turnover=85.0,
        max_drawdown=-0.082,
    )
    defaults.update(overrides)
    return DashboardState(**defaults)


# ── DashboardState construction ─────────────────────────────────────────────


class TestDashboardStateConstruction:
    def test_basic_construction(self) -> None:
        state = _make_state()
        assert state.mode == "PAPER"
        assert len(state.positions) == 2
        assert state.cash_usd == 50_000.0

    def test_default_alerts_and_falsification(self) -> None:
        """Default factory produces empty lists when not supplied."""
        state = DashboardState(
            mode="PAPER",
            positions={},
            cash_usd=0,
            unrealized_pnl=0,
            daily_returns=pd.Series(dtype=float),
            regime_state="BULL",
            exposure=0.0,
            factor_health={},
            factor_ic={},
            attribution={},
            last_rebalance_date="",
            last_rebalance_trades=0,
            last_rebalance_cost_usd=0,
            fill_rate=0,
            slippage_bps=0,
        )
        assert state.alerts == []
        assert state.falsification_results == []
        assert state.cost_drag_annual == 0.0


# ── Demo state ──────────────────────────────────────────────────────────────


class TestGenerateDemoState:
    def test_demo_state_valid(self) -> None:
        state = _generate_demo_state()
        assert state.mode == "PAPER"
        assert len(state.positions) == 20
        assert state.cash_usd > 0
        assert len(state.daily_returns) == 252
        assert len(state.factor_health) > 0
        assert len(state.alerts) > 0
        assert len(state.falsification_results) == 8

    def test_demo_factor_health_consistent_with_ic(self) -> None:
        state = _generate_demo_state()
        for factor, health in state.factor_health.items():
            ic = state.factor_ic[factor]
            assert health == ic_to_health(ic)

    def test_demo_max_drawdown_computed(self) -> None:
        state = _generate_demo_state()
        assert state.max_drawdown < 0  # some drawdown expected


# ── IC-to-health color mapping ──────────────────────────────────────────────


class TestICToHealth:
    def test_high_ic_green(self) -> None:
        assert ic_to_health(0.05) == "G"

    def test_boundary_green(self) -> None:
        assert ic_to_health(IC_THRESHOLDS["green"]) == "G"

    def test_medium_ic_yellow(self) -> None:
        assert ic_to_health(0.02) == "Y"

    def test_boundary_yellow(self) -> None:
        assert ic_to_health(IC_THRESHOLDS["yellow"]) == "Y"

    def test_low_ic_red(self) -> None:
        assert ic_to_health(0.01) == "R"

    def test_zero_ic_red(self) -> None:
        assert ic_to_health(0.0) == "R"

    def test_negative_ic_red(self) -> None:
        assert ic_to_health(-0.01) == "R"


# ── Alerts sorted by date ──────────────────────────────────────────────────


class TestAlertsSorting:
    @patch("nyse_ats.monitoring.dashboard.st")
    def test_alerts_sorted_by_date_descending(self, mock_st: MagicMock) -> None:
        state = _make_state(
            alerts=[
                {"level": "I", "date": "2026-04-09", "message": "old"},
                {"level": "W", "date": "2026-04-13", "message": "recent"},
                {"level": "I", "date": "2026-04-11", "message": "middle"},
            ]
        )
        render_alerts(state)
        # Verify markdown calls were made (alerts rendered)
        assert mock_st.markdown.call_count == 3
        # First call should contain the most recent date
        first_call = mock_st.markdown.call_args_list[0][0][0]
        assert "2026-04-13" in first_call

    @patch("nyse_ats.monitoring.dashboard.st")
    def test_empty_alerts_shows_info(self, mock_st: MagicMock) -> None:
        state = _make_state(alerts=[])
        render_alerts(state)
        mock_st.info.assert_called_once()


# ── Falsification panel data structure ──────────────────────────────────────


class TestFalsificationPanel:
    @patch("nyse_ats.monitoring.dashboard.st")
    def test_renders_all_triggers(self, mock_st: MagicMock) -> None:
        state = _make_state()
        render_falsification_panel(state)
        # 3 triggers in fixture -> 3 markdown calls
        assert mock_st.markdown.call_count == 3

    @patch("nyse_ats.monitoring.dashboard.st")
    def test_empty_results_shows_info(self, mock_st: MagicMock) -> None:
        state = _make_state(falsification_results=[])
        render_falsification_panel(state)
        mock_st.info.assert_called_once()

    @patch("nyse_ats.monitoring.dashboard.st")
    def test_veto_fired_shows_no_entry(self, mock_st: MagicMock) -> None:
        state = _make_state(
            falsification_results=[
                {"trigger_id": "F3", "passed": False, "severity": "VETO", "value": -0.30, "threshold": -0.25},
            ]
        )
        render_falsification_panel(state)
        call_text = mock_st.markdown.call_args_list[0][0][0]
        assert "VETO FIRED" in call_text

    @patch("nyse_ats.monitoring.dashboard.st")
    def test_warning_fired_shows_warning(self, mock_st: MagicMock) -> None:
        state = _make_state(
            falsification_results=[
                {
                    "trigger_id": "F4",
                    "passed": False,
                    "severity": "WARNING",
                    "value": 0.20,
                    "threshold": 0.15,
                },
            ]
        )
        render_falsification_panel(state)
        call_text = mock_st.markdown.call_args_list[0][0][0]
        assert "WARNING FIRED" in call_text


# ── Mode color mapping ─────────────────────────────────────────────────────


class TestModeColorMapping:
    def test_paper_mode_blue(self) -> None:
        assert MODE_COLORS["PAPER"] == "blue"

    def test_shadow_mode_orange(self) -> None:
        assert MODE_COLORS["SHADOW"] == "orange"

    def test_live_mode_red(self) -> None:
        assert MODE_COLORS["LIVE"] == "red"

    @patch("nyse_ats.monitoring.dashboard.st")
    def test_header_renders_mode(self, mock_st: MagicMock) -> None:
        state = _make_state(mode="LIVE")
        render_header(state)
        mock_st.title.assert_called_once_with("NYSE ATS Dashboard")
        md_call = mock_st.markdown.call_args_list[0][0][0]
        assert "LIVE" in md_call
        assert "red" in md_call


# ── Empty positions handled ─────────────────────────────────────────────────


class TestEmptyPositions:
    @patch("nyse_ats.monitoring.dashboard.st")
    def test_empty_positions_renders_zero(self, mock_st: MagicMock) -> None:
        state = _make_state(positions={})
        render_portfolio_section(state)
        # metric called for Positions, Cash, P&L
        assert mock_st.metric.call_count == 3
        # First metric call is Positions with value 0
        first_metric = mock_st.metric.call_args_list[0]
        assert first_metric[0][1] == 0


# ── Empty returns handled ──────────────────────────────────────────────────


class TestEmptyReturns:
    @patch("nyse_ats.monitoring.dashboard.st")
    def test_empty_returns_shows_info(self, mock_st: MagicMock) -> None:
        state = _make_state(daily_returns=pd.Series(dtype=float))
        render_charts(state)
        mock_st.info.assert_called_once()

    def test_compute_drawdown_empty_series(self) -> None:
        result = compute_drawdown_series(pd.Series(dtype=float))
        assert len(result) == 0

    def test_compute_max_drawdown_empty(self) -> None:
        assert compute_max_drawdown(pd.Series(dtype=float)) == 0.0


# ── Attribution sums ───────────────────────────────────────────────────────


class TestAttribution:
    def test_attribution_sums_to_total(self) -> None:
        state = _make_state()
        total = sum(state.attribution.values())
        expected = 0.012 + (-0.003) + (-0.001)
        assert abs(total - expected) < 1e-10

    @patch("nyse_ats.monitoring.dashboard.st")
    def test_empty_attribution_shows_info(self, mock_st: MagicMock) -> None:
        state = _make_state(attribution={})
        render_attribution(state)
        mock_st.info.assert_called_once()

    @patch("nyse_ats.monitoring.dashboard.st")
    def test_attribution_renders_factors(self, mock_st: MagicMock) -> None:
        state = _make_state()
        render_attribution(state)
        # 3 factors + 1 total line = 4 markdown calls
        assert mock_st.markdown.call_count == 4


# ── Drawdown percentage calculation ────────────────────────────────────────


class TestDrawdownCalculation:
    def test_drawdown_from_known_series(self) -> None:
        # 10% up, then 20% down from peak
        returns = pd.Series([0.10, -0.20])
        dd = compute_drawdown_series(returns)
        # After +10%: cum=1.10, peak=1.10, dd=0
        # After -20%: cum=0.88, peak=1.10, dd=(0.88-1.10)/1.10 = -0.2
        assert abs(dd.iloc[-1] - (-0.2)) < 1e-10

    def test_max_drawdown_from_known_series(self) -> None:
        returns = pd.Series([0.10, -0.20, 0.05])
        max_dd = compute_max_drawdown(returns)
        assert max_dd < 0
        assert abs(max_dd - (-0.2)) < 1e-10

    def test_all_positive_returns_zero_drawdown(self) -> None:
        returns = pd.Series([0.01, 0.02, 0.01])
        max_dd = compute_max_drawdown(returns)
        assert max_dd == 0.0

    def test_drawdown_never_positive(self) -> None:
        np.random.seed(99)
        returns = pd.Series(np.random.normal(0, 0.02, 100))
        dd = compute_drawdown_series(returns)
        assert (dd <= 0.0 + 1e-14).all()


# ── Render smoke tests (verify no exceptions) ──────────────────────────────


class TestRenderSmoke:
    @patch("nyse_ats.monitoring.dashboard.st")
    def test_render_risk_metrics_no_error(self, mock_st: MagicMock) -> None:
        mock_st.progress = MagicMock()
        state = _make_state()
        render_risk_metrics(state)

    @patch("nyse_ats.monitoring.dashboard.st")
    def test_render_factor_health_no_error(self, mock_st: MagicMock) -> None:
        state = _make_state()
        render_factor_health(state)
        assert mock_st.markdown.call_count == 3

    @patch("nyse_ats.monitoring.dashboard.st")
    def test_render_last_rebalance_no_error(self, mock_st: MagicMock) -> None:
        state = _make_state()
        render_last_rebalance(state)
        assert mock_st.markdown.call_count >= 5
