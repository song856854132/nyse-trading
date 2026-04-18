"""Streamlit real-time risk dashboard for NYSE ATS.

Launch: streamlit run src/nyse_ats/monitoring/dashboard.py

Reads state from DuckDB (live.duckdb) or accepts injected data dicts
for testing. All heavy computation delegates to nyse_core pure functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Dashboard data protocol ─────────────────────────────────────────────────


@dataclass
class DashboardState:
    """Snapshot of system state for dashboard rendering."""

    mode: str  # "PAPER", "SHADOW", "LIVE"
    positions: dict[str, float]  # symbol -> weight
    cash_usd: float
    unrealized_pnl: float
    daily_returns: pd.Series  # historical daily returns
    regime_state: str  # "BULL" or "BEAR"
    exposure: float  # 0.0 - 1.0
    factor_health: dict[str, str]  # factor_name -> "G" / "Y" / "R"
    factor_ic: dict[str, float]  # factor_name -> rolling IC
    attribution: dict[str, float]  # factor_name -> return contribution
    last_rebalance_date: str
    last_rebalance_trades: int
    last_rebalance_cost_usd: float
    fill_rate: float
    slippage_bps: float
    alerts: list[dict] = field(default_factory=list)
    # [{"level": "W", "date": "...", "message": "..."}]
    falsification_results: list[dict] = field(default_factory=list)
    # [{trigger_id, passed, severity, value, threshold}]
    cost_drag_annual: float = 0.0
    annual_turnover: float = 0.0
    max_drawdown: float = 0.0


# ── Color / label helpers ───────────────────────────────────────────────────

MODE_COLORS: dict[str, str] = {
    "PAPER": "blue",
    "SHADOW": "orange",
    "LIVE": "red",
}

HEALTH_EMOJI: dict[str, str] = {
    "G": ":green_circle:",
    "Y": ":yellow_circle:",
    "R": ":red_circle:",
}

ALERT_STYLE: dict[str, tuple[str, str]] = {
    "V": ("VETO", ":red_square:"),
    "W": ("WARNING", ":orange_square:"),
    "I": ("INFO", ":blue_square:"),
}

IC_THRESHOLDS: dict[str, float] = {
    "green": 0.03,
    "yellow": 0.015,
}


def ic_to_health(ic_value: float) -> str:
    """Map an IC value to a health color code (G/Y/R)."""
    if ic_value >= IC_THRESHOLDS["green"]:
        return "G"
    if ic_value >= IC_THRESHOLDS["yellow"]:
        return "Y"
    return "R"


# ── Computation helpers ─────────────────────────────────────────────────────


def compute_drawdown_series(daily_returns: pd.Series) -> pd.Series:
    """Compute running drawdown series from daily returns."""
    if daily_returns is None or len(daily_returns) == 0:
        return pd.Series(dtype=float)
    cumulative = (1 + daily_returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    return drawdown


def compute_max_drawdown(daily_returns: pd.Series) -> float:
    """Compute maximum drawdown from daily returns."""
    dd = compute_drawdown_series(daily_returns)
    if len(dd) == 0:
        return 0.0
    return float(dd.min())


# ── Render functions ────────────────────────────────────────────────────────


def render_header(state: DashboardState) -> None:
    """Render title bar with mode indicator."""
    st.title("NYSE ATS Dashboard")
    color = MODE_COLORS.get(state.mode, "gray")
    st.markdown(f"**Mode:** :{color}[{state.mode}]")


def render_portfolio_section(state: DashboardState) -> None:
    """Left column: positions, cash, P&L."""
    st.subheader("Portfolio")
    n_positions = len(state.positions)
    st.metric("Positions", n_positions)
    st.metric("Cash", f"${state.cash_usd:,.0f}")

    pnl_delta = f"{state.unrealized_pnl:+,.0f}"
    st.metric("Unrealized P&L", f"${state.unrealized_pnl:,.0f}", delta=pnl_delta)

    if state.positions:
        with st.expander("Position weights"):
            for sym, wt in sorted(state.positions.items(), key=lambda x: x[1], reverse=True):
                st.text(f"  {sym:6s}  {wt:6.1%}")


def render_risk_metrics(state: DashboardState) -> None:
    """Right column: drawdown bar, cost drag, regime, exposure."""
    st.subheader("Risk Metrics")

    # Drawdown bar against F3 threshold (-25%)
    f3_threshold = -0.25
    dd_pct = state.max_drawdown * 100
    dd_ratio = min(abs(state.max_drawdown / f3_threshold), 1.0) if f3_threshold != 0 else 0.0

    if abs(state.max_drawdown) < 0.10:
        dd_color = "green"
    elif abs(state.max_drawdown) < 0.20:
        dd_color = "orange"
    else:
        dd_color = "red"

    st.markdown(f"**Drawdown:** {dd_pct:.1f}% (F3 limit: {f3_threshold * 100:.0f}%) :{dd_color}_circle:")
    st.progress(dd_ratio)

    # Cost drag (PRIMARY monitoring metric)
    cost_ok = state.cost_drag_annual < 5.0
    cost_label = "OK" if cost_ok else "HIGH"
    st.markdown(f"**Cost Drag:** {state.cost_drag_annual:.1f}% annual [{cost_label}]")

    # Regime
    regime_icon = ":chart_with_upwards_trend:" if state.regime_state == "BULL" else ":bear:"
    st.markdown(f"**Regime:** {state.regime_state} {regime_icon}")

    # Exposure
    st.markdown(f"**Exposure:** {state.exposure:.0%}")

    # Turnover
    st.markdown(f"**Annual Turnover:** {state.annual_turnover:.0f}%")


def render_factor_health(state: DashboardState) -> None:
    """Factor health panel with color indicators."""
    st.subheader("Factor Health")

    for factor_name, health in state.factor_health.items():
        emoji = HEALTH_EMOJI.get(health, ":white_circle:")
        ic_val = state.factor_ic.get(factor_name, 0.0)
        st.markdown(f"{emoji} **{factor_name}** (IC: {ic_val:.3f})")


def render_attribution(state: DashboardState) -> None:
    """Brinson-style factor attribution display."""
    st.subheader("Attribution")

    if not state.attribution:
        st.info("No attribution data available.")
        return

    for factor, contrib in sorted(state.attribution.items(), key=lambda x: x[1], reverse=True):
        sign = "+" if contrib >= 0 else ""
        st.markdown(f"  {factor}: {sign}{contrib:.1%}")

    total = sum(state.attribution.values())
    st.markdown(f"  **Total:** {total:+.1%}")


def render_last_rebalance(state: DashboardState) -> None:
    """Last rebalance summary."""
    st.subheader("Last Rebalance")
    st.markdown(f"**Date:** {state.last_rebalance_date}")
    st.markdown(f"**Trades:** {state.last_rebalance_trades}")
    st.markdown(f"**Cost est:** ${state.last_rebalance_cost_usd:,.0f}")
    st.markdown(f"**Fill rate:** {state.fill_rate:.0%}")
    st.markdown(f"**Slippage:** {state.slippage_bps:.1f} bps")


def render_alerts(state: DashboardState) -> None:
    """Alert timeline (last 7 days)."""
    st.subheader("Alerts (last 7 days)")

    if not state.alerts:
        st.info("No alerts in the last 7 days.")
        return

    sorted_alerts = sorted(state.alerts, key=lambda a: a.get("date", ""), reverse=True)

    for alert in sorted_alerts:
        level = alert.get("level", "I")
        label, icon = ALERT_STYLE.get(level, ("INFO", ":blue_square:"))
        alert_date = alert.get("date", "?")
        msg = alert.get("message", "")
        st.markdown(f"{icon} **[{label}]** {alert_date}: {msg}")


def render_charts(state: DashboardState) -> None:
    """Cumulative returns chart + drawdown chart using plotly."""
    st.subheader("Performance Charts")

    if state.daily_returns is None or len(state.daily_returns) == 0:
        st.info("No return history available for charting.")
        return

    cumulative = (1 + state.daily_returns).cumprod() - 1
    drawdown = compute_drawdown_series(state.daily_returns)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=cumulative.index,
            y=cumulative.values,
            mode="lines",
            name="Cumulative Return",
            line={"color": "steelblue"},
        )
    )
    fig.update_layout(
        title="Cumulative Returns",
        yaxis_tickformat=".1%",
        height=300,
        margin={"l": 40, "r": 20, "t": 40, "b": 30},
    )
    st.plotly_chart(fig, use_container_width=True)

    # Drawdown chart
    dd_fig = go.Figure()
    dd_fig.add_trace(
        go.Scatter(
            x=drawdown.index,
            y=drawdown.values,
            mode="lines",
            name="Drawdown",
            fill="tozeroy",
            line={"color": "crimson"},
        )
    )
    dd_fig.add_hline(y=-0.25, line_dash="dash", line_color="red", annotation_text="F3: -25%")
    dd_fig.update_layout(
        title="Drawdown",
        yaxis_tickformat=".1%",
        height=250,
        margin={"l": 40, "r": 20, "t": 40, "b": 30},
    )
    st.plotly_chart(dd_fig, use_container_width=True)


def render_falsification_panel(state: DashboardState) -> None:
    """F1-F8 trigger status panel."""
    st.subheader("Falsification Triggers (F1-F8)")

    if not state.falsification_results:
        st.info("No falsification data available.")
        return

    for result in state.falsification_results:
        trigger_id = result.get("trigger_id", "?")
        passed = result.get("passed", True)
        severity = result.get("severity", "WARNING")
        value = result.get("value", 0.0)
        threshold = result.get("threshold", 0.0)

        if passed:
            icon = ":white_check_mark:"
            status = "OK"
        elif severity == "VETO":
            icon = ":no_entry:"
            status = "VETO FIRED"
        else:
            icon = ":warning:"
            status = "WARNING FIRED"

        st.markdown(f"{icon} **{trigger_id}** - {status} (value: {value:.3f}, threshold: {threshold:.3f})")


# ── Demo data generation ───────────────────────────────────────────────────


def _generate_demo_state() -> DashboardState:
    """Demo state for development/testing with realistic values."""
    np.random.seed(42)
    n_days = 252
    today = date(2026, 4, 16)
    dates = pd.bdate_range(end=today, periods=n_days)
    daily_ret = pd.Series(
        np.random.normal(0.0004, 0.012, n_days),
        index=dates,
    )

    positions = {
        "AAPL": 0.052,
        "MSFT": 0.051,
        "JNJ": 0.050,
        "JPM": 0.050,
        "UNH": 0.049,
        "PG": 0.049,
        "V": 0.049,
        "HD": 0.048,
        "MA": 0.048,
        "PFE": 0.047,
        "ABBV": 0.047,
        "KO": 0.047,
        "PEP": 0.046,
        "MRK": 0.046,
        "COST": 0.046,
        "TMO": 0.045,
        "AVGO": 0.045,
        "WMT": 0.045,
        "LLY": 0.050,
        "ACN": 0.050,
    }

    factor_ic: dict[str, float] = {
        "IVOL": 0.042,
        "Piotroski": 0.038,
        "EarnSurp": 0.022,
        "52wHigh": 0.035,
        "Momentum": 0.031,
        "ShortInt": 0.012,
        "Accruals": 0.033,
    }
    factor_health = {name: ic_to_health(ic) for name, ic in factor_ic.items()}

    attribution: dict[str, float] = {
        "IVOL": 0.012,
        "Piotroski": 0.008,
        "EarnSurp": 0.004,
        "52wHigh": 0.006,
        "Momentum": -0.003,
        "ShortInt": -0.001,
        "Accruals": 0.005,
    }

    alerts = [
        {"level": "W", "date": "2026-04-13", "message": "ShortInt IC dropped below 0.015"},
        {"level": "I", "date": "2026-04-11", "message": "Weekly rebalance completed (3 trades)"},
        {"level": "I", "date": "2026-04-09", "message": "Regime confirmed BULL (SPY > SMA200)"},
    ]

    falsification_results = [
        {
            "trigger_id": "F1_signal_death",
            "passed": True,
            "severity": "VETO",
            "value": 0.050,
            "threshold": 0.010,
        },
        {"trigger_id": "F2_factor_death", "passed": True, "severity": "VETO", "value": 1.0, "threshold": 3.0},
        {
            "trigger_id": "F3_excessive_drawdown",
            "passed": True,
            "severity": "VETO",
            "value": -0.082,
            "threshold": -0.250,
        },
        {
            "trigger_id": "F4_concentration",
            "passed": True,
            "severity": "WARNING",
            "value": 0.052,
            "threshold": 0.150,
        },
        {
            "trigger_id": "F5_turnover_spike",
            "passed": True,
            "severity": "WARNING",
            "value": 85.0,
            "threshold": 200.0,
        },
        {"trigger_id": "F6_cost_drag", "passed": True, "severity": "WARNING", "value": 1.8, "threshold": 5.0},
        {
            "trigger_id": "F7_regime_anomaly",
            "passed": True,
            "severity": "WARNING",
            "value": 0.0,
            "threshold": 0.0,
        },
        {
            "trigger_id": "F8_data_staleness",
            "passed": True,
            "severity": "WARNING",
            "value": 2.0,
            "threshold": 10.0,
        },
    ]

    max_dd = compute_max_drawdown(daily_ret)

    return DashboardState(
        mode="PAPER",
        positions=positions,
        cash_usd=42_000.0,
        unrealized_pnl=3_240.0,
        daily_returns=daily_ret,
        regime_state="BULL",
        exposure=1.0,
        factor_health=factor_health,
        factor_ic=factor_ic,
        attribution=attribution,
        last_rebalance_date="2026-04-11",
        last_rebalance_trades=5,
        last_rebalance_cost_usd=127.0,
        fill_rate=1.0,
        slippage_bps=4.2,
        alerts=alerts,
        falsification_results=falsification_results,
        cost_drag_annual=1.8,
        annual_turnover=85.0,
        max_drawdown=max_dd,
    )


def _load_state_or_demo() -> DashboardState:
    """Load from DuckDB or generate demo state for development.

    Phase 5 will connect this to actual live.duckdb. For now
    the demo state provides realistic values for UI development.
    """
    # TODO: Phase 5 — connect to live.duckdb
    # try:
    #     import duckdb
    #     con = duckdb.connect("live.duckdb", read_only=True)
    #     ...
    # except Exception:
    #     pass
    return _generate_demo_state()


# ── Main entry point ───────────────────────────────────────────────────────


def main() -> None:
    """Entry point for Streamlit app."""
    st.set_page_config(page_title="NYSE ATS", layout="wide")

    state = _load_state_or_demo()

    render_header(state)

    col1, col2 = st.columns([1, 2])
    with col1:
        render_portfolio_section(state)
        render_factor_health(state)
    with col2:
        render_risk_metrics(state)
        render_attribution(state)
        render_last_rebalance(state)

    render_charts(state)
    render_falsification_panel(state)
    render_alerts(state)


if __name__ == "__main__":
    main()
